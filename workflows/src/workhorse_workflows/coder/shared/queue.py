"""The main graph's queue spine: pick an epic, pick a story, branch, record the outcome.

Ports `init-base.py`, `branch-story.py`, `select-next-epic.py`, `branch-epic.py`,
`select-next-story.py`, `flag-epic-blocked.py`, `prune-epic.py` and `commit-story.py` —
every non-agent node the main graph runs between its sub-flows.

They are one module because they are one loop, and because they only make sense together:
`select_epic` skips what `flag_epic_blocked` wrote, `select_story` skips what the skip set
holds, and `prune_epic` pops what both of them declined to. Splitting them by verb would
have put each half of a contract in a different file.

`flag-qa-failure.py` and its docs-block sibling are gone rather than ported-and-kept. They
committed a story behind a `needs manual review` marker and let the queue go on, and the
review they named never happened — `Coder.give_up` and `Coder.blocked_docs` now end the run
instead.

Three ports are worth naming:

* **`SPEC_DIR` becomes a parameter.** `branch-story.py` read the story's spec dir from
  `os.environ.get("SPEC_DIR", f"docs/specs/{slug}")`, and nothing in the workflow ever set
  that variable — the default was the behavior. It is a defaulted argument here, so an
  operator override is still possible and is now visible at the callsite.
* **`prune-epic.py`'s optional JSON sidecar stays.** Its `argv[2]` was unused by the graph,
  but it is the documented back-compat path that mirrors `select_epic`'s own sidecar
  precedence, so it is a defaulted parameter rather than a deletion.
* **One legacy fallback stays** — the `epics-todo.json` sidecar in `select_epic` and
  `prune_epic`, for repos and sandboxes whose graph ostler cannot answer for. `select_story`
  has none: a story's blockers live in its own `story.md`, which only ostler parses.

`emit(...)` / `sys.exit(0)` becomes a returned model, as everywhere else in this package.
The one script that exited **non-zero** — `branch-epic.py`, when the checkout fails —
raises `WorkflowFailed`, which is the same refusal: a failed checkout must halt the node,
not report success while HEAD stayed wherever it was.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ostler import Ostler, markdown, path as okf_path, registry
from workhorse import worklist as wl
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import find_docs_root, find_repo_root, load_json
from workhorse_workflows.coder.shared import commits, paths, story_status
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.worktree import untouched_since
from workhorse_workflows.coder.shared.schemas.queue import (
    BaseBranch,
    EpicBlocked,
    EpicBranch,
    EpicPick,
    EpicPruned,
    RunScope,
    StoryBranch,
    StoryCommitted,
    StoryPick,
    StoryStamped,
    WorktreeCleanliness,
)
from workhorse_workflows.kit import (
    active_branch,
    branch_exists,
    branch_merged,
    branch_owner,
    checkout,
    commit_all,
    commit_paths,
    current_branch,
    default_branch,
    get_affected_repos,
    GitError,
    is_ancestor,
    local_branch_exists,
    merge_ref,
    open_repo,
    resolve_workspace,
    restore_paths,
    show_file,
)

#: The legacy JSON queue's filename, kept as a fallback for repos and sandboxes with no
#: doc graph. It sits beside `index.md`, wherever ostler puts that.
LEGACY_QUEUE_NAME = "epics-todo.json"


def legacy_queue(root: Path) -> Path:
    """The legacy JSON queue for *root*, beside the ostler-managed `index.md`."""
    return okf_path.epics_root_in(root) / LEGACY_QUEUE_NAME


def _has_queue_bullet(content: str) -> bool:
    """Whether *content* holds at least one `- [epic](…)` queue entry.

    What a real queue looks like, so a git hiccup that returns some other file cannot
    silently wipe the local copy during reconciliation. Parsed, so an index whose only
    bullet-shaped line sits inside a fenced example does not qualify as a queue.
    """
    return any(b.bracketed[0] for b in markdown.split(content).walk_bullets())


#: Epics set aside for the rest of THIS run, one name per line, inside the run dir.
BLOCKED_FILE = "blocked-epics.txt"

#: Stories given up for the rest of THIS run, one slug per line, inside the run dir.
SKIP_FILE = "qa-skip-stories.txt"

#: Epic branches THIS run put itself on, one ref per line, inside the run dir.
CLAIMED_FILE = "epic-branches.txt"

#: Matches `ostler.select`'s done tokens, which is what makes a story read as done to
#: `ostler next-story`.
DONE_STATUS = "QA passed"


# ── the base branch and the two branch-cutting nodes ──────────────────────────────


def _resolve_trunk(root: Path) -> str:
    """The repo's trunk: `origin/HEAD`, else local `main`, else local `master`, else `main`."""
    trunk = default_branch(root)
    if trunk:
        return trunk
    if branch_exists(root, "main"):
        return "main"
    if branch_exists(root, "master"):
        return "master"
    return "main"


@blueprint.node
def begin_run(logger: logging.Logger, run_dir: str = "") -> RunScope:
    """Drop the skip state a previous run left behind in this run dir.

    `blocked-epics.txt`, `qa-skip-stories.txt` and `epic-branches.txt` all say "for the rest
    of THIS run", and all live in the run dir — which is fine while a run dir belongs to one run. It does
    not: workhorse derives the run id from `--params`, so the same command lands in the same
    stable dir every time, and a *fresh* run there inherits the last one's verdicts. The
    contradiction was visible in the log — a run ended with "all 1 queued epic(s) were set
    aside this run … start a new run to retry them", and the new run read that same file and
    ended on the same sentence before reaching a single node. Every retry was a no-op, which
    for an unattended queue reads as "nothing left to do".

    So the lifecycle is the workflow's to own, not the dir's: whatever a resume keeps (a
    resume never re-enters `start`), a new run starts with an empty skip set.
    """
    if not run_dir:
        return RunScope()
    path = Path(run_dir)
    cleared = []
    for name in (BLOCKED_FILE, SKIP_FILE, CLAIMED_FILE):
        stale = path / name
        if stale.exists():
            stale.unlink()
            cleared.append(name)
    if cleared:
        logger.info("cleared %s left by a previous run in this run dir", ", ".join(cleared))
    return RunScope(cleared=cleared)


@blueprint.node
def init_base(logger: logging.Logger, repo_dir: str = "") -> BaseBranch:
    """Resolve the branch an epic's PR will be opened against, before anything is cut.

    The current branch is preferred, because a run started from a release branch should
    PR back into it. It is rejected when HEAD is detached or empty, and when it still
    points at a `feat/`/`rewrite/` branch a prior run left checked out — PR-ing an epic
    into another epic's branch is how a queue quietly stops reaching trunk.
    """
    root = find_repo_root(repo_dir)
    base = active_branch(root)
    if not base or base.startswith("feat/") or base.startswith("rewrite/"):
        base = _resolve_trunk(root)
    logger.info("base branch is '%s'", base)
    return BaseBranch(base_branch=base)


def _branch_repo(logger: logging.Logger, repo_path: Path, repo_name: str, branch: str) -> bool:
    """Cut or check out `branch` in one repo. False when the path is not a git repo.

    An existing branch is checked out WITHOUT resetting it, which is what makes a resumed
    story keep the commits it already made.
    """
    if not (repo_path / ".git").exists():
        logger.warning("%s: not a git repo, skipping", repo_name)
        return False
    if local_branch_exists(repo_path, branch):
        checkout(repo_path, branch)
        logger.info("%s: checked out existing %s", repo_name, branch)
    else:
        checkout(repo_path, branch, create=True)
        logger.info("%s: created %s", repo_name, branch)
    return True


@blueprint.node
def branch_story(
    logger: logging.Logger,
    story: str = "",
    docs_path: str = "",
    spec_dir: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> StoryBranch:
    """Cut the working branch for a single story, in the docs repo and every affected repo.

    The branch name is the slug, with no prefix — story mode's branches are not epic
    branches and must not be archived aside by `branch_epic`. The base is read from the
    docs repo *before* the new branch is cut, since afterwards there is nothing to read it
    from.

    Idempotent in every repo: a resumed story checks its branch out rather than recreating
    it. Repos come from the story's `plan-context.json` through the workspace, so a story
    that has not been planned yet branches only the docs repo — which is exactly what the
    first pass wants.
    """
    slug = story or "story"
    branch = slug
    docs_root = find_docs_root(docs_path, repo_dir)

    base_branch = "main"
    if (docs_root / ".git").exists():
        base_branch = current_branch(docs_root)
        if not base_branch or base_branch == branch:
            base_branch = "main"

    branched: list[str] = []
    if _branch_repo(logger, docs_root, docs_root.name, branch):
        branched.append(docs_root.name)

    spec_dir_rel = spec_dir or f"docs/specs/{slug}"
    plan_ctx = load_json(
        docs_root / spec_dir_rel / "plan-context.json", "plan-context.json", logger
    )
    repos = resolve_workspace(workspace_file, repo_dir)
    for repo_name in get_affected_repos(plan_ctx, repos):
        repo_path = Path(repos[repo_name]["path"])
        if repo_path == docs_root:
            continue  # already branched above
        if _branch_repo(logger, repo_path, repo_name, branch):
            branched.append(repo_name)

    return StoryBranch(base_branch=base_branch, story_branch=branch, repos=branched)


def _claimed_branches(run_dir: str) -> set[str]:
    """The epic branches this run has already put itself on."""
    if not run_dir:
        return set()
    try:
        text = (Path(run_dir) / CLAIMED_FILE).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {line.strip() for line in text.splitlines() if line.strip()}


def _record_claim(run_dir: str, branch: str) -> None:
    """Remember that this run owns `branch`, so a later visit recognises it."""
    if not run_dir or not branch:
        return
    path = Path(run_dir)
    if not path.is_dir():
        return
    claimed = _claimed_branches(run_dir)
    if branch in claimed:
        return
    (path / CLAIMED_FILE).write_text(
        "\n".join(sorted(claimed | {branch})) + "\n", encoding="utf-8"
    )


def _claim_epic_branch(
    logger: logging.Logger, root: Path, branch: str, base: str, run_dir: str = ""
) -> None:
    """Put this run on `feat/<epic>`, or refuse and say why.

    There are exactly five states an existing branch of that name can be in, and they
    want five different answers:

    ============================  =========================================
    State                         Action
    ============================  =========================================
    Held by another working tree  Hard error — another run is on it
    Held by *this* working tree   Continue on it, no reset
    Claimed earlier by this run   Check it out again, merge `base` in, no reset
    Merged into base              Reset to HEAD and reuse
    Unmerged, nobody's            Hard error — real work, a human decides
    ============================  =========================================

    The "claimed earlier" row is what makes a multi-epic drain survivable. Ownership used
    to be inferred solely from "is it checked out right now", which is true only of the
    epic in hand — so the moment the drain set an epic aside, moved to the next one and
    later came back, its *own* branch read as unmerged work by a stranger and the run died
    on a hard error. `epic-branches.txt` is the run's memory of what it cut, and it is
    run-scoped for the same reason the skip ledgers are: a fresh run in the same dir
    inherits no claim, so the refusal below still protects a genuinely foreign branch.

    This replaces renaming the branch aside to `archive/<epic>-<sha>`. That was
    reasonable while a leftover ref landed in a container-local clone that
    `down -v` destroyed. Under worktrees the refs land in the **operator's own
    repo**, so every re-run left a permanent `archive/*` in their `git branch` —
    and archival renamed *every* existing branch, merged or not, to defend against
    one case: a squash-merged branch that has since diverged. The table above
    handles that case directly (`branch_merged` sees a squash merge; a diverged one
    fails both tests and is refused) and refuses the genuinely dangerous case
    instead of silently renaming past it.

    Refusing rather than working around is deliberate, and it is the one place this
    workflow prefers a hard stop to an unattended recovery: the alternatives are
    discarding somebody's unmerged commits or continuing an epic on top of an
    unrelated branch's content, and neither is something a run should decide alone.
    """
    if not branch_exists(root, branch):
        if not checkout(root, branch, create=True):
            raise WorkflowFailed(f"failed to create epic branch {branch}")
        _record_claim(run_dir, branch)
        return

    owner = branch_owner(root, branch)
    if owner is not None:
        if Path(owner).resolve() != Path(root).resolve():
            raise WorkflowFailed(
                f"{branch} is checked out in another working tree ({owner}) — another "
                f"run is working this epic. Wait for it, or run a different epic."
            )
        logger.info("resuming %s, already checked out here", branch)
        _record_claim(run_dir, branch)
        return

    if branch in _claimed_branches(run_dir):
        logger.info("returning to %s, which this run cut earlier", branch)
        if not checkout(root, branch):
            raise WorkflowFailed(f"failed to return to epic branch {branch}")
        _catch_up_with_base(logger, root, branch, base)
        return

    if branch_merged(root, branch, base):
        logger.info("%s is already merged into %s — reusing the name from HEAD", branch, base)
        if not checkout(root, branch, reset=True):
            raise WorkflowFailed(f"failed to reset merged epic branch {branch}")
        return

    raise WorkflowFailed(
        f"{branch} already exists with commits that are not in {base or 'the base branch'}. "
        f"That is unmerged work this run did not create — merge it, or delete the branch, "
        f"then start the epic again."
    )


def _base_ref(root: Path, base: str) -> str:
    """`base` as it resolves in this repo — the local branch, else `origin/<base>`, else "".

    Mirrors :func:`branch_merged`'s resolution, for the same reason: a container may hold
    only the remote-tracking ref.
    """
    if not base:
        return ""
    for ref in (base, f"origin/{base}") if "/" not in base else (base,):
        if branch_exists(root, ref):
            return ref
    return ""


def _catch_up_with_base(logger: logging.Logger, root: Path, branch: str, base: str) -> None:
    """Bring `base` into an epic branch this run cut before `base` moved on without it.

    A multi-epic drain cuts `feat/<epic>` from whatever HEAD was at the time, sets the
    epic aside, finishes and **merges** other epics into `base`, then comes back. The
    branch it comes back to is now behind by every epic that landed meanwhile — so it
    carries a stale copy of their story files, their specs and the epic queue itself.

    That staleness is not cosmetic, and it is not confined to this branch. Three things
    go wrong, in escalating order:

    * The reviewers read it as truth. A story that reached `QA passed` on `base` still
      says `QA give-up … needs manual review` here, so `code-review` files a finding
      against work that is finished and merged, and `apply-review` spends a lap
      "fixing" it.
    * :func:`_reconcile_queue` patches the queue file back — as an *uncommitted* edit,
      which is exactly the shape a reviewer reads as an unexplained local change. It was
      observed being reverted with `git checkout --`, which restored the stale queue.
    * Whatever survives to the squash merge lands on `base`: a finished epic back in the
      work queue, and a passed story's status reverted to its give-up string. The next
      `select_epic` then re-selects an epic that is already merged and redoes it.

    Merging `base` in fixes all three at the source, and is a no-op in the ordinary case
    where nothing landed while the epic was aside. A conflict means two epics genuinely
    edited the same lines, which is not something a run should resolve unattended — the
    merge is aborted (see :func:`merge_ref`) and this refuses, in keeping with this
    module's stance everywhere else that ownership is ambiguous.
    """
    ref = _base_ref(root, base)
    if not ref or is_ancestor(root, ref, branch):
        return
    if not merge_ref(root, ref):
        raise WorkflowFailed(
            f"{ref} does not merge cleanly into {branch}, which this run cut before {ref} "
            f"moved. Two epics edited the same lines — resolve it by hand, then start the "
            f"epic again."
        )
    logger.info("merged %s into %s, which had been set aside while %s moved", ref, branch, ref)


def _reconcile_queue(logger: logging.Logger, root: Path, base: str) -> None:
    """Restore the epic queue from `base`, when `base` has an authoritative copy of it.

    Guarded twice — the base's copy must be non-empty and must look like a real queue —
    because the failure this protects against is a git hiccup silently wiping the queue,
    which reads downstream as "every epic is merged".

    **It commits what it writes.** Left uncommitted, the restored queue is a bare working
    tree edit with nothing explaining it, and the reviewers a few nodes later read exactly
    that: `code-review` filed it as a finding ("removes an epic from the work queue"), and
    `apply-review` resolved the finding with `git checkout --`, putting the stale queue
    back and spending a lap doing it. A queue reconcile is the run's own bookkeeping, so
    it is recorded like the run's other bookkeeping rather than left looking like
    somebody's unfinished edit. The usual case writes identical content and
    `commit_paths` finds nothing staged, so no commit is made.

    "Identical" needs the trailing newline put back. `git show` drops it, so writing back
    what it returns left the queue file one byte dirty on *every* epic — a diff with no
    change in it, which the first story of each epic then swept into its own commit. That
    stray byte was also enough to make a story that built nothing look like a story that
    built something, to anything downstream reading "did this story change the tree".
    """
    if not base or not branch_exists(root, base):
        return
    queue_rel = paths.epics_index(root)
    content = show_file(root, base, queue_rel)
    if content is None or not content.strip() or not _has_queue_bullet(content):
        return
    if not content.endswith("\n"):
        content += "\n"
    (root / queue_rel).write_text(content, encoding="utf-8")
    reconcile = commits.message(
        "chore", commits.scope(root.name), f"reconcile the epic queue to {base}"
    )
    if commit_paths(root, reconcile, queue_rel):
        logger.info("reconciled index.md to %s", base)


@blueprint.node
def branch_epic(
    logger: logging.Logger,
    epic: str = "",
    base_branch: str = "",
    run_dir: str = "",
    repo_dir: str = "",
) -> EpicBranch:
    """Put this run on `feat/<epic>`, cutting it from HEAD when it does not exist yet.

    An existing branch of that name is not assumed stale and not assumed ours — see
    :func:`_claim_epic_branch` for the five states it can be in and why four of them
    have an answer other than "rename it aside".

    The queue is reconciled from the base afterwards, so an epic branch cut from a stale
    HEAD still walks the queue the base branch has.
    """
    root = find_repo_root(repo_dir)
    restore_paths(root, paths.epics_index(root))

    if epic:
        _claim_epic_branch(logger, root, f"feat/{epic}", base_branch, run_dir.strip())

    _reconcile_queue(logger, root, base_branch)
    return EpicBranch(working_epic=epic, epic_branch=f"feat/{epic}")


# ── epic selection ────────────────────────────────────────────────────────────────


def _queue_from_ostler(okf: Ostler) -> list[str] | None:
    try:
        return [str(x) for x in okf.todo()]
    except (OSError, ValueError, RuntimeError):
        return None


def _queue_from_json(root: Path) -> list[str] | None:
    """Fallback: the legacy `epics-todo.json` queue file, for repos with no doc graph."""
    todo = legacy_queue(root)
    if not todo.is_file():
        return None
    try:
        data = json.loads(todo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return [str(x) for x in data] if isinstance(data, list) else None


def _run_dir_path(root: Path, run_dir: str) -> Path:
    """A run dir as given, resolved against the docs root when it is relative."""
    path = Path(run_dir)
    return path if path.is_absolute() else root / path


def epics_set_aside(root: Path, run_dir: str) -> list[str]:
    """Epics set aside THIS run by `flag_epic_blocked`. Missing dir or file → empty.

    Public because `open_pr` needs it too: an epic branch is cut from HEAD, so it carries
    whatever a set-aside epic left there, and a PR that ships it would merge past the very
    gate that set it aside.
    """
    if not run_dir:
        return []
    try:
        text = (_run_dir_path(root, run_dir) / BLOCKED_FILE).read_text(encoding="utf-8")
    except OSError:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


@blueprint.node
def select_epic(
    logger: logging.Logger, docs_path: str = "", run_dir: str = "", repo_dir: str = ""
) -> EpicPick:
    """Return the front epic of the queue that has not been set aside this run.

    The queue is walked front-to-back, one PR per epic; `prune_epic` pops a merged epic off
    the front so the next call here returns the following one. Story selection within an
    epic is a separate concern (`select_story`).

    Selection goes through the shared worklist primitive rather than re-deriving "front
    item not in the skip set", so remaining-work counts reach telemetry in the same shape
    every workflow's queue uses. It is read-only: pruning stays ostler-native in
    `prune_epic`, so no worklist backend is involved.
    """
    root = find_docs_root(docs_path, repo_dir)
    okf = Ostler(root)

    epics = _queue_from_ostler(okf)
    if epics is None or (not epics and _queue_from_json(root) is not None):
        # ostler is unavailable, or answered empty while a legacy epics-todo.json exists —
        # fall back to the JSON file so test sandboxes and legacy repos still work.
        json_epics = _queue_from_json(root)
        if json_epics is not None:
            epics = json_epics
    if epics is None:
        reason = "could not read the epics queue (ostler todo list)"
        logger.warning("%s", reason)
        return EpicPick(reason=reason)
    if not epics:
        reason = "epic queue is empty — every epic has been merged"
        logger.info("%s", reason)
        return EpicPick(reason=reason)

    blocked = epics_set_aside(root, run_dir)
    items = [wl.WorkItem(id=e, status="pending", order=i) for i, e in enumerate(epics)]
    nxt = wl.select_next(items, skip=blocked)
    if nxt is None:
        # Every queued epic was set aside. Loud, because the run is about to end and this
        # is invisible otherwise: the queue is still full and nothing was merged. (An
        # empty queue was reported above, so reaching here always means "all set aside".)
        logger.warning(
            "all %d queued epic(s) were set aside this run (%s) — ending the run with the "
            "queue intact; start a new run to retry them",
            len(epics),
            ", ".join(blocked),
        )
        return EpicPick(
            reason=(
                f"all {len(epics)} queued epic(s) were set aside this run "
                f"({', '.join(blocked)}) — nothing was merged; start a new run to retry"
            )
        )

    if blocked:
        logger.info("skipping %d epic(s) set aside this run (%s)", len(blocked), ", ".join(blocked))
    logger.info("selected epic '%s'", nxt.id)
    return EpicPick(has_epic=True, epic=nxt.id)


@blueprint.node
def flag_epic_blocked(
    logger: logging.Logger, epic: str = "", run_dir: str = "", detail: str = ""
) -> EpicBlocked:
    """Set a blocked epic aside for the rest of this run, and report the whole set.

    `select_story` reports `blocked` when an epic still has unbuilt stories but none is
    runnable — given up this run, waiting on a dependency nothing will satisfy, or never
    authored. That is not a finished epic, so it must not take the `prune_epic` → PR →
    merge path: its remaining scope would be merged as if it had been built.

    Halting instead would be the wrong trade for an unattended queue, where one stuck epic
    would stop every independent epic behind it. Three properties make setting it aside
    safe: each pass sets aside exactly one epic and the queue is finite, so the loop
    terminates; nothing is lost, because the epic keeps its place in the index and its work
    stays committed on its own unmerged branch; and the set is per-run, so a later run
    retries it.
    """
    epic = epic.strip()
    if not epic:
        logger.warning("flag_epic_blocked called with no epic — nothing to set aside")
        return EpicBlocked(reason="no epic supplied")

    blocked = _record_blocked(run_dir.strip(), epic)
    reason = (
        f"epic '{epic}' set aside for this run"
        + (f": {detail.strip()}" if detail.strip() else "")
        + " — NOT merged; its branch keeps whatever it built"
    )
    # Warning, not info: an unattended run that ends with epics set aside looks exactly
    # like one that finished the queue unless this is visible in the log.
    logger.warning("%s", reason)
    return EpicBlocked(epic_blocked=True, blocked_epics=",".join(blocked), reason=reason)


def _record_blocked(run_dir: str, epic: str) -> list[str]:
    """Append `epic` to the per-run blocked set and return the whole set, in order.

    No run dir (story mode, or a hand-run node) means no per-run state to keep, so the epic
    is simply reported — the caller still routes away from `prune_epic`, which is the part
    that must not happen.
    """
    if not run_dir or not epic:
        return [epic] if epic else []
    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    blocked_path = path / BLOCKED_FILE
    existing = (
        blocked_path.read_text(encoding="utf-8").splitlines() if blocked_path.exists() else []
    )
    existing = [ln.strip() for ln in existing if ln.strip()]
    if epic not in existing:
        with blocked_path.open("a", encoding="utf-8") as f:
            f.write(f"{epic}\n")
        existing.append(epic)
    return existing


def _prune_json_sidecar(todo_path: Path, epic: str) -> bool:
    """Back-compat: pop the epic from an explicit JSON queue array."""
    if not todo_path.is_file():
        return False
    try:
        epics = json.loads(todo_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(epics, list) or epic not in epics:
        return False
    epics.remove(epic)  # first occurrence (the front, in normal pop-front operation)
    try:
        todo_path.write_text(json.dumps(epics, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


@blueprint.node
def prune_epic(
    logger: logging.Logger, epic: str = "", todo_path: str = "", repo_dir: str = ""
) -> EpicPruned:
    """Pop a merged epic off the front of the queue.

    Called once an epic's PR has been gated and merged (or passed through offline), so that
    `select_epic` returns the following epic on the next iteration.

    Idempotent and best-effort throughout: a missing index, an absent epic or a write
    failure is not fatal, because a stale entry only costs one extra no-op PR/merge cycle.
    The root is `paths.epics_repo_root()` — `agents.yml` or a `docs/epics/` **directory**,
    not `.git` — which is this node alone, and is what lets a bind-mounted docs clone with
    no `.git` still have its queue popped.
    """
    if not epic:
        logger.info("no epic given — nothing to prune")
        return EpicPruned()

    root = paths.epics_repo_root(repo_dir)

    # An explicit sidecar path wins, matching select_epic's own queue precedence.
    if todo_path.strip():
        sidecar = Path(todo_path.strip())
        if not sidecar.is_absolute():
            sidecar = root / sidecar
        logger.info("explicit sidecar %s given — pruning '%s' from it", sidecar, epic)
        return EpicPruned(pruned=_prune_json_sidecar(sidecar, epic))

    # ostler first, then the legacy epics-todo.json — the same fallback order as select_epic.
    try:
        res = Ostler(root).todo_prune(epic)
        pruned = bool(res.ok)
    except (OSError, ValueError, RuntimeError):
        pruned = False
    if pruned:
        logger.info("pruned '%s' via the ostler-managed epics queue", epic)
        return EpicPruned(pruned=True)

    logger.info("'%s' not found via ostler — falling back to epics-todo.json", epic)
    return EpicPruned(pruned=_prune_json_sidecar(legacy_queue(root), epic))


# ── story selection ───────────────────────────────────────────────────────────────


def _progress_fields(report: dict | str) -> tuple[str, int]:
    """Queue progress for the dashboard, through the shared worklist snapshot.

    The story queue *is* a worklist — `report['done']` finished items plus the
    `report['remaining']` not-done slugs — so those are handed to `worklist.snapshot`
    rather than formatted here, and coder's stories read the same `done/total` shape every
    workflow's queue will. Best-effort: a legacy or failed report yields empty fields, and
    the labels simply carry no progress.
    """
    if not isinstance(report, dict):
        return "", 0
    done = int(report.get("done") or 0)
    remaining = [str(s) for s in (report.get("remaining") or [])]
    items = [wl.WorkItem(id=f"__done_{i}", status="done") for i in range(done)]
    items += [wl.WorkItem(id=s, status="pending") for s in remaining]
    snap = wl.snapshot(items)
    return snap.progress, snap.remaining


def _next_story_report(okf: Ostler, epic: str, skip: set[str]) -> dict | str:
    """Ostler's next-story report, or `""` on a tooling failure.

    `skip` (slugs given up this run) is passed into ostler so a given-up story is not
    re-offered — without it, that story stays first-runnable forever and the epic prunes
    with other stories unbuilt.

    The *report* rather than `next_story`: it distinguishes "done" from "blocked", which is
    the whole difference between merging an epic and setting it aside.
    """
    try:
        return okf.next_story_report(epic, skip=skip)
    except (OSError, ValueError, RuntimeError):
        return ""


def _load_skip_set(root: Path, run_dir: str) -> set[str]:
    """The per-run skip set: story slugs to leave alone for the REST OF THIS RUN.

    Nothing in the workflow writes this file any more — a give-up ends the run rather than
    skipping the story. It is kept as the **operator's** lever: a run that died on a story
    you have decided not to fix is resumed past it by writing the slug into
    `<run_dir>/qa-skip-stories.txt` before the resume. That is a deliberate, recorded human
    decision, which is exactly what the automatic version was not.

    Missing dir or file → empty set, so this is a no-op on every run nobody has touched.
    """
    if not run_dir:
        return set()
    try:
        text = (_run_dir_path(root, run_dir) / SKIP_FILE).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {ln.strip() for ln in text.splitlines() if ln.strip()}


@blueprint.node
def select_story(
    logger: logging.Logger,
    epic: str = "",
    docs_path: str = "",
    run_dir: str = "",
    repo_dir: str = "",
) -> StoryPick:
    """Select the next runnable story within `epic`, or say why there is none.

    **"No story" is not one answer, and the graph must not treat it as one.** An epic can
    run out of runnable stories because it is finished, because its remaining stories were
    given up on this run, because they wait on a dependency nothing will satisfy, or
    because they were never authored. Only the first means "merge it". So this returns
    `story_outcome`, and the graph branches on that:

    * `story` — build it;
    * `done` — prune the epic, open its PR, merge;
    * `blocked` — set the epic aside for this run and move to the next one. Its committed
      work stays on its branch, unmerged; a later run picks it up again.

    It is the outcome — not the mere absence of a story — that decides whether an epic is
    merged. Conflating the two is what merged an epic with 20 of 21 stories unbuilt after
    one story gave up on QA.
    """
    if not epic:
        logger.warning("no epic supplied to select_story")
        return StoryPick(
            reason="no epic supplied to select_story (epic selection is select_epic)"
        )

    root = find_docs_root(docs_path, repo_dir)
    okf = Ostler(root)
    skip = _load_skip_set(root, run_dir)

    report = _next_story_report(okf, epic, skip)
    progress, remaining_count = _progress_fields(report)
    found = StoryPick(epic=epic, progress=progress, remaining_count=remaining_count)

    # One narrowing for the whole tail: `_next_story_report` answers `""` on a tooling
    # failure, and everything below reads a key off the report — so the failure becomes an
    # empty mapping here, rather than an `isinstance` repeated at each read.
    fields: dict = report if isinstance(report, dict) else {}
    state = fields.get("state", "")
    nxt = fields.get("story")

    # Selection is skip-aware at the ostler level, so a given-up story is never handed back
    # here. This guard only fires if that contract regresses.
    forced_by_skip = isinstance(nxt, dict) and str(nxt.get("slug", "")) in skip
    if forced_by_skip:
        nxt, state = None, "blocked"

    if state == "done":
        logger.info("%s", fields["detail"])
        return found.model_copy(update={"story_outcome": "done", "reason": fields["detail"]})
    if state == "blocked":
        detail = (
            fields["detail"]
            if not forced_by_skip
            else f"the story ostler offered for epic '{epic}' was given up this run"
        )
        logger.warning("epic '%s' is blocked: %s", epic, detail)
        return found.model_copy(
            update={
                "reason": (
                    f"{detail} — setting this epic aside for this run; its work stays on its "
                    "branch, unmerged, and a later run retries it"
                )
            }
        )

    # A story ostler did not offer is not a story: with no graph answer there is nothing to
    # select from, and merging an epic we cannot read would ship it unbuilt.
    if not nxt:
        return found.model_copy(
            update={
                "reason": (
                    f"ostler could not select a story for epic '{epic}' — setting it aside "
                    "rather than merging an epic whose story graph did not answer"
                )
            }
        )

    slug = str(nxt.get("slug"))
    # Final guard: never hand back a story in this run's skip set (the fallback already
    # excludes them, so this only fires if a selection path regressed).
    if slug in skip:
        logger.warning("story '%s' was given up this run — stopping to avoid re-grinding", slug)
        return found.model_copy(
            update={
                "reason": (
                    f"story '{slug}' was given up this run — setting the epic aside to avoid "
                    "re-grinding; start a new run or clear the skip set to retry"
                )
            }
        )

    try:
        spec_dir = okf.spec_path(slug) or f"docs/specs/{slug}"
    except (OSError, ValueError, RuntimeError):
        spec_dir = f"docs/specs/{slug}"

    logger.info("selected story '%s' in epic '%s'", slug, epic)
    return found.model_copy(
        update={
            "story_outcome": "story",
            "story_path": str(nxt.get("path") or ""),
            "spec_dir": spec_dir,
            "story_slug": slug,
        }
    )


# ── recording an outcome ──────────────────────────────────────────────────────────


def _stamp_status(
    logger: logging.Logger, root: Path, epic: str, slug: str, story_path: str
) -> tuple[bool, bool]:
    """Record `QA passed` on the story and commit just that change.

    Returns `(was it written, did it supersede a previous attempt's outcome)`.

    Committed SEPARATELY from the story's own work and scoped to the paths the stamp
    touched, so recording that a story passed can never sweep in working-tree changes the
    story deliberately left alone. It is a `docs` commit rather than the story's `feat`
    for the same reason: it moves a status line and no code, and typing it as the story
    would cut a second release for the act of recording the first.

    `superseded` is the narrower half of the answer: this stamp replaced a *previous
    attempt's* outcome — a give-up, a docs block, an interrupted run — rather than the
    `Not started` a story carries before anything has touched it. A re-run of work that
    already landed under a failure marker produces no diff at all by construction, and the
    stamp moving is the only evidence the pass happened.
    """
    before = story_status.current(root, slug, epic=epic, story_path=story_path)
    written = story_status.mark(root, slug, DONE_STATUS, epic=epic, story_path=story_path, logger=logger)
    if not written:
        logger.warning(
            "status '%s' NOT recorded for %s — it will be re-selected on the next loop",
            DONE_STATUS,
            slug,
        )
        return False, False
    prior = before.strip()
    superseded = bool(prior) and prior not in (registry.DEFAULT_STORY_STATUS, DONE_STATUS)

    # The story doc lives in the workflow host repo (the doc graph root), which is not
    # necessarily one of the affected code repos — so it is committed here or not at all.
    # Scoped to the stamped paths so this can never sweep in unrelated working-tree changes
    # the story deliberately left alone.
    specs: list[str] = []
    for path in written:
        try:
            specs.append(str(path.resolve().relative_to(root.resolve())))
        except ValueError:
            logger.info("status file %s is outside %s — not committing it here", path, root)
    # `docs`, not the story's own `feat`: this commit moves a status line and no code, and
    # typing it as the story would bump a version for the act of recording that the story
    # passed — a second release for work the story's own commit already released.
    stamp = commits.message(
        "docs",
        commits.scope(root.name),
        f"mark {slug} {DONE_STATUS}",
        epic=epic,
        story=slug,
    )
    if specs and commit_paths(root, stamp, *specs):
        logger.info("recorded %s for %s", DONE_STATUS, slug)
    return True, superseded


def _commit_roots(
    logger: logging.Logger,
    root: Path,
    spec_dir: str,
    workspace_file: str,
    repo_dir: str,
    roots: list[str] | None,
) -> list[tuple[str, Path]]:
    """Which checkouts this story's commit covers — the caller's list, or the plan's.

    A caller that already knows where the work went says so. The fix drain does: it has no
    plan context to read the affected repos off, because its one-turn item lane produces
    none, so it asks git which repositories are holding changes and hands the answer here.
    Without that the plan lookup below falls back to the resolved root, which silently
    leaves a second repo's half of the repair uncommitted.

    The package name is the checkout's own directory name, which is what the workspace
    manifest keys a repo by and what release-please knows the package as.
    """
    if roots:
        return [(Path(p).name, Path(p)) for p in roots]
    return _affected_roots(logger, root, spec_dir, workspace_file, repo_dir)


def _affected_roots(
    logger: logging.Logger, root: Path, spec_dir: str, workspace_file: str, repo_dir: str
) -> list[tuple[str, Path]]:
    """The repos this story's plan says it touched, as `(package name, checkout)` pairs.

    Read from the story's own `plan-context.json`, which is the only record of where the
    work went — the workspace manifest lists every repo the run *may* touch, not the ones
    it did. A plan naming nothing falls back to the resolved root, which is the
    single-repo case and every sandbox with no seeded plan.

    Shared by the two nodes that have to agree on the answer: the one that commits and the
    one that checks the commit happened. A repo listed in the plan but missing on disk, or
    not a git checkout, is warned about and dropped — its absence is not this story's
    defect and neither node can do anything about it.
    """
    repos = resolve_workspace(workspace_file, repo_dir)
    spec = root / spec_dir if spec_dir else None
    plan_ctx = (
        load_json(spec / "plan-context.json", "plan-context.json", logger)
        if spec and spec.exists()
        else {}
    )
    affected = get_affected_repos(plan_ctx, repos)
    if not affected:
        logger.info("no affected repos resolved from plan-context — falling back to the repo root")
        return [(root.name, root)]

    found: list[tuple[str, Path]] = []
    for name in affected:
        repo_path = Path(repos.get(name, {}).get("path", ""))
        if not repo_path.is_dir():
            logger.warning("repo %s path not found: %s", name, repo_path)
            continue
        if not (repo_path / ".git").exists():
            logger.warning("repo %s is not a git repo — skipping", name)
            continue
        found.append((name, repo_path))
    return found


def _uncommitted(root: Path) -> list[str]:
    """Every path in *root* holding work that is not in a commit yet.

    Staged, unstaged and untracked alike: all three are work the agent produced and did
    not record, and the whole point of the check is that a story ends in commits. An
    unreadable repo — or one with no commit to diff against yet — reports nothing, which
    is the conservative answer for a gate whose other arm parks the run.
    """
    try:
        repo = open_repo(root)
        dirty = {item.a_path for item in repo.index.diff(None) if item.a_path}
        dirty |= set(repo.untracked_files)
        try:
            dirty |= {item.a_path for item in repo.index.diff("HEAD") if item.a_path}
        except (GitError, OSError, TypeError, ValueError, KeyError):
            pass  # an unborn HEAD has nothing to compare the index against
    except (GitError, OSError, TypeError, ValueError, RuntimeError):
        return []
    return sorted(dirty)


@blueprint.node
def check_repos_clean(
    logger: logging.Logger,
    story_slug: str = "",
    spec_dir: str = "",
    preexisting: list[str] | None = None,
    repo_dir: str = "",
    workspace_file: str = "",
) -> WorktreeCleanliness:
    """Did the agent commit its own work in every repo the story touched?

    The replacement for committing on the agent's behalf. `commit_all` decided the
    subject, the scope and the boundary of a story's commits from outside the work and
    swept whatever else was on disk into them; the agent knows all three and commits at
    will now, so what is left for the workflow is the check — and a dirty tree at this
    point means work that was produced and not recorded, which is the failure the sweep
    was hiding.

    `preexisting` is `snapshot_worktree_state`'s reading from before the first dev turn.
    Whatever it recorded and the story has not since touched is subtracted, so an
    operator's leftovers never park a run the agent finished cleanly. The subtraction is
    one-directional by construction — see `shared/worktree.py`.
    """
    root = find_repo_root(repo_dir)
    snapshot = tuple(preexisting or ())
    dirty: list[str] = []
    names: list[str] = []
    for name, repo_path in _affected_roots(logger, root, spec_dir, workspace_file, repo_dir):
        names.append(name)
        excused = untouched_since(repo_path, snapshot)
        dirty.extend(
            f"{name}:{rel}"
            for rel in _uncommitted(repo_path)
            if rel not in excused and not paths.is_gate_context(rel)
        )

    slug = story_slug or "story"
    if dirty:
        logger.info(
            "%s left %d uncommitted path(s) behind: %s",
            slug, len(dirty), ", ".join(dirty[:10]) + (" …" if len(dirty) > 10 else ""),
        )
    else:
        logger.info("%s left nothing uncommitted in %s", slug, ", ".join(names) or "the repo root")
    return WorktreeCleanliness(clean=not dirty, dirty=dirty, repos=names)


@blueprint.node
def stamp_story_passed(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    story_path: str = "",
    repo_dir: str = "",
) -> StoryStamped:
    """Record the story's passing outcome, and commit that one line.

    All that is left of `commit_story` on the main graph's success path once the code
    commits belong to the agent. It stays a node because it is queue integrity rather than
    development work: story selection reads the status line, so an agent that forgets it
    re-runs the story forever and the epic never completes.
    """
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)
    stamped, superseded = _stamp_status(logger, root, epic, slug, story_path)
    return StoryStamped(stamped=stamped, superseded_outcome=superseded)


@blueprint.node
def commit_story(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    spec_dir: str = "",
    story_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
    kind: str = "feat",
    roots: list[str] | None = None,
) -> StoryCommitted:
    """Commit a completed story's changes in each affected code repo, then stamp it passed.

    Commits only in repos where implementation work was done, resolved from
    `plan-context.json`. The docs repo is never committed to here unless it appears in the
    affected repos list — i.e. unless it was an implementation target rather than merely
    the workflow host.

    This is also where a story's PASSING outcome is recorded. Nothing else on the success
    path writes that status, and story selection reads it, not the git log: without the
    stamp a story that just passed is re-selected on the next loop iteration and its epic
    never reads as complete. The stamp happens AFTER the code commits, so `committed`
    measures the story's WORK and nothing else, and so a crash between the two leaves the
    story un-stamped — retried — rather than marked done with no work behind it.

    `kind` is the Conventional Commit type these commits carry, and it defaults to `feat`
    because that is what a story is: documented behavior that did not exist before. The one
    caller that overrides it is the fix drain, whose items are filed defects — see
    `commits` for why the type is not guessed per story.
    """
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)

    # The epic's sequence number is a folder-ordering device, not part of its name, so the
    # trailer reads `Epic: fixes` whether the caller handed us `fixes` or `0004-fixes`.
    epic_name = registry.epic_slug(epic) or epic
    description = commits.story_description(root, story_path, slug)

    # Each repo's commit is scoped to that repo's own name, because that is the name its
    # release-please config knows the package by — one story touching three repos produces
    # three subjects, each releasing the component it actually changed.
    def _story_message(package: str) -> str:
        return commits.message(
            kind, commits.scope(package), description, epic=epic_name, story=slug
        )

    def _commit_in(repo_path: Path, package: str) -> bool:
        """``commit_all``, with a git refusal turned into a halt rather than a False.

        False here means the tree held nothing to commit, and callers read it as "this
        story did no work". A stale ``index.lock``, a rejecting hook or a failed signature
        is the opposite situation — the story's work exists and git would not record it —
        so it must halt loudly here, while the tree still holds the work and the git error
        is still in hand, rather than be reported as an idle story."""
        try:
            return bool(commit_all(repo_path, _story_message(package)))
        except GitError as exc:
            raise WorkflowFailed(
                f"git refused the commit for {slug} in {repo_path}: {exc}"
            ) from exc

    any_committed = False
    for name, repo_path in _commit_roots(logger, root, spec_dir, workspace_file, repo_dir, roots):
        if _commit_in(repo_path, name):
            logger.info("committed in %s", repo_path.name)
            any_committed = True

    _, superseded = _stamp_status(logger, root, epic, slug, story_path)
    return StoryCommitted(committed=any_committed, superseded_outcome=superseded)


__all__ = [
    "branch_epic",
    "branch_story",
    "check_repos_clean",
    "commit_story",
    "flag_epic_blocked",
    "init_base",
    "prune_epic",
    "select_epic",
    "select_story",
    "stamp_story_passed",
]
