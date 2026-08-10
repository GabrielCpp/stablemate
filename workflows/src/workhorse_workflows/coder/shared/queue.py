"""The main graph's queue spine: pick an epic, pick a story, branch, record the outcome.

Ports `init-base.py`, `branch-story.py`, `select-next-epic.py`, `branch-epic.py`,
`select-next-story.py`, `flag-epic-blocked.py`, `prune-epic.py`, `commit-story.py` and
`flag-qa-failure.py` — every non-agent node the main graph runs between its sub-flows.

They are one module because they are one loop, and because they only make sense together:
`select_epic` skips what `flag_epic_blocked` wrote, `select_story` skips what
`flag_qa_failure` wrote, and `prune_epic` pops what both of them declined to. Splitting
them by verb would have put each half of a contract in a different file.

Three ports are worth naming:

* **`SPEC_DIR` becomes a parameter.** `branch-story.py` read the story's spec dir from
  `os.environ.get("SPEC_DIR", f"docs/specs/{slug}")`, and nothing in the workflow ever set
  that variable — the default was the behavior. It is a defaulted argument here, so an
  operator override is still possible and is now visible at the callsite.
* **`prune-epic.py`'s optional JSON sidecar stays.** Its `argv[2]` was unused by the graph,
  but it is the documented back-compat path that mirrors `select_epic`'s own sidecar
  precedence, so it is a defaulted parameter rather than a deletion.
* **The legacy fallbacks stay too** — the `epics-todo.json` sidecar in `select_epic` and
  `prune_epic`, `dependencies.json` in `select_story`. Both exist for repos and sandboxes
  whose graph ostler cannot answer for, and both are load-bearing in the tests.

`emit(...)` / `sys.exit(0)` becomes a returned model, as everywhere else in this package.
The one script that exited **non-zero** — `branch-epic.py`, when the checkout fails —
raises `WorkflowFailed`, which is the same refusal: a failed checkout must halt the node,
not report success while HEAD stayed wherever it was.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ostler import Ostler, markdown, model, path as okf_path, registry, select
from workhorse import worklist as wl
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import find_docs_root, find_repo_root, load_json
from workhorse_workflows.coder.shared import commits, paths, story_status
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.queue import (
    BaseBranch,
    DocsBlockFlagged,
    EpicBlocked,
    EpicBranch,
    EpicPick,
    EpicPruned,
    QaFlagged,
    RunScope,
    StoryBranch,
    StoryCommitted,
    StoryPick,
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
    find_open_pr,
    get_affected_repos,
    GitError,
    local_branch_exists,
    resolve_github_token,
    resolve_repo,
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

#: Matches `ostler.select`'s done tokens, which is what makes a story read as done to
#: `ostler next-story` and to `select_story`'s `dependencies.json` fallback.
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

    `blocked-epics.txt` and `qa-skip-stories.txt` say "set aside for the rest of THIS run",
    and both live in the run dir — which is fine while a run dir belongs to one run. It does
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
    for name in (BLOCKED_FILE, SKIP_FILE):
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


def _claim_epic_branch(logger: logging.Logger, root: Path, branch: str, base: str) -> None:
    """Put this run on `feat/<epic>`, or refuse and say why.

    There are exactly four states an existing branch of that name can be in, and they
    want four different answers:

    ============================  =========================================
    State                         Action
    ============================  =========================================
    Held by another working tree  Hard error — another run is on it
    Merged into base              Reset to HEAD and reuse
    Unmerged, nobody's            Hard error — real work, a human decides
    Held by *this* working tree   Continue on it, no reset
    ============================  =========================================

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
        return

    owner = branch_owner(root, branch)
    if owner is not None:
        if Path(owner).resolve() != Path(root).resolve():
            raise WorkflowFailed(
                f"{branch} is checked out in another working tree ({owner}) — another "
                f"run is working this epic. Wait for it, or run a different epic."
            )
        logger.info("resuming %s, already checked out here", branch)
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


def _reconcile_queue(logger: logging.Logger, root: Path, base: str) -> None:
    """Restore the epic queue from `base`, when `base` has an authoritative copy of it.

    Guarded twice — the base's copy must be non-empty and must look like a real queue —
    because the failure this protects against is a git hiccup silently wiping the queue,
    which reads downstream as "every epic is merged".
    """
    if not base or not branch_exists(root, base):
        return
    queue_rel = paths.epics_index(root)
    content = show_file(root, base, queue_rel)
    if content is None or not content.strip() or not _has_queue_bullet(content):
        return
    (root / queue_rel).write_text(content, encoding="utf-8")
    logger.info("reconciled index.md to %s", base)


@blueprint.node
def branch_epic(
    logger: logging.Logger, epic: str = "", base_branch: str = "", repo_dir: str = ""
) -> EpicBranch:
    """Put this run on `feat/<epic>`, cutting it from HEAD when it does not exist yet.

    An existing branch of that name is not assumed stale and not assumed ours — see
    :func:`_claim_epic_branch` for the four states it can be in and why three of them
    have an answer other than "rename it aside".

    The queue is reconciled from the base afterwards, so an epic branch cut from a stale
    HEAD still walks the queue the base branch has.
    """
    root = find_repo_root(repo_dir)
    restore_paths(root, paths.epics_index(root))

    if epic:
        _claim_epic_branch(logger, root, f"feat/{epic}", base_branch)

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


def _progress_fields(report: dict | str) -> tuple[str, str]:
    """Queue progress for the dashboard, through the shared worklist snapshot.

    The story queue *is* a worklist — `report['done']` finished items plus the
    `report['remaining']` not-done slugs — so those are handed to `worklist.snapshot`
    rather than formatted here, and coder's stories read the same `done/total` shape every
    workflow's queue will. Best-effort: a legacy or failed report yields empty fields, and
    the labels simply carry no progress.
    """
    if not isinstance(report, dict):
        return "", ""
    done = int(report.get("done") or 0)
    remaining = [str(s) for s in (report.get("remaining") or [])]
    items = [wl.WorkItem(id=f"__done_{i}", status="done") for i in range(done)]
    items += [wl.WorkItem(id=s, status="pending") for s in remaining]
    snap = wl.snapshot(items)
    return snap.progress, str(snap.remaining)


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


def _is_done(story_md: Path) -> bool:
    """Whether a story.md declares a done status — ostler's parse, ostler's verdict.

    Used only by the legacy `dependencies.json` fallback, where there is no graph to ask.
    It still must not disagree with the graph: the status is read as the *field*
    (frontmatter `status:`, else the parsed `- **Status**:` bullet) and judged by
    `ostler.select.is_done`. The old check was `"QA passed" in <whole file>`, which a story
    whose prose merely mentions QA passing satisfies — a story could be skipped as built
    while still unbuilt, and its dependents would unblock on it.
    """
    try:
        doc = markdown.split(story_md.read_text(encoding="utf-8"))
    except OSError:
        return False
    return select.is_done(model.story_status(doc))


def _load_skip_set(root: Path, run_dir: str) -> set[str]:
    """The per-run skip set: story slugs `flag_qa_failure` has given up THIS run.

    Missing dir or file → empty set, so this is a no-op on the first pass and on any run
    that never gave up a story.
    """
    if not run_dir:
        return set()
    try:
        text = (_run_dir_path(root, run_dir) / SKIP_FILE).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {ln.strip() for ln in text.splitlines() if ln.strip()}


def _next_from_json(root: Path, epic: str, skip: set[str]) -> dict | None | str:
    """Fallback: the first runnable story in the epic's `dependencies.json`.

    Returns a dict `{slug, path}`, `None` when every story is DONE, or `""` on error. A
    skipped story is NOT treated as done — its dependents stay blocked, since they depend
    on work that did not pass.

    `None` means *done* and nothing else. The not-done-but-not-runnable cases each get
    their own sentinel (`_all_skipped`, `_blocked`, `_missing_story_md`, `_no_dep_file`)
    because the caller merges the epic on "done" — so an epic that still has unbuilt
    stories in it must never come back as `None`.
    """
    dep_file = paths.epic_dir(root, epic) / "dependencies.json"
    if not dep_file.is_file():
        return {"_no_dep_file": True}  # sentinel: caller reports the specific reason
    try:
        data = json.loads(dep_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    stories = data.get("stories")
    if not isinstance(stories, list):
        return ""

    done: set[str] = set()
    for entry in stories:
        slug = str(entry.get("slug", ""))
        path = entry.get("path", "")
        story_md = Path(path) if path else paths.story_md(root, epic, slug)
        if _is_done(story_md):
            done.add(slug)

    skipped_runnable = False  # a story that WOULD run but for the per-run skip set
    waiting: list[str] = []  # not done, not runnable: deps unmet
    for entry in stories:
        slug = str(entry.get("slug", ""))
        if slug in done:
            continue
        if any(d not in done for d in entry.get("dependencies", [])):
            waiting.append(slug)
            continue
        if slug in skip:
            # Runnable (deps satisfied) but given up this run — exclude, and remember we
            # did, so the caller can report "stopped on skip" rather than "all done".
            skipped_runnable = True
            continue
        path = entry.get("path", "")
        if not path:
            path = str(paths.story_md(root, epic, slug))
        if not Path(path).is_file():
            # Listed in the DAG but not authored yet → its own reason.
            return {"_missing_story_md": path}
        return {"slug": slug, "path": path}

    if skipped_runnable:
        return {"_all_skipped": True}
    if waiting:
        return {"_blocked": waiting}
    return None  # all done


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

    `has_story` is still returned for anything reading it, but it is the outcome — not its
    absence — that decides whether an epic is merged. Conflating the two is what merged an
    epic with 20 of 21 stories unbuilt after one story gave up on QA.
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

    # Fall back to dependencies.json only when ostler could not answer at all: it failed
    # (""), the epic is not in its graph, or the epic carries no stories there. A real
    # ostler verdict is authoritative — consulting the legacy file after it would let a
    # missing dependencies.json override a correct "all done".
    if not nxt:
        json_nxt = _next_from_json(root, epic, skip)
        if isinstance(json_nxt, dict) and json_nxt.get("_no_dep_file"):
            return found.model_copy(
                update={
                    "reason": (
                        f"no dependencies.json found for epic '{epic}' — cannot select a story; "
                        "setting it aside rather than merging an epic we cannot read"
                    )
                }
            )
        if isinstance(json_nxt, dict) and json_nxt.get("_all_skipped"):
            return found.model_copy(
                update={
                    "reason": (
                        f"remaining runnable stories in epic '{epic}' were all given up this "
                        "run — setting it aside; start a new run or clear the skip set to retry"
                    )
                }
            )
        if isinstance(json_nxt, dict) and json_nxt.get("_blocked"):
            return found.model_copy(
                update={
                    "reason": (
                        f"remaining stories in epic '{epic}' wait on unmet dependencies "
                        f"({', '.join(json_nxt['_blocked'])}) — setting it aside"
                    )
                }
            )
        if isinstance(json_nxt, dict) and json_nxt.get("_missing_story_md"):
            return found.model_copy(
                update={
                    "reason": (
                        f"next story's story.md not found: {json_nxt['_missing_story_md']} — "
                        "unauthored scope, so this epic is set aside rather than merged"
                    )
                }
            )
        if isinstance(json_nxt, dict) and "slug" in json_nxt:
            nxt = json_nxt
        elif json_nxt is None:
            return found.model_copy(
                update={"story_outcome": "done", "reason": f"every story in epic '{epic}' is done"}
            )
        else:
            return found.model_copy(
                update={"reason": f"could not read the story DAG for epic '{epic}' — setting it aside"}
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
            "has_story": True,
            "story_outcome": "story",
            "story_path": str(nxt.get("path") or ""),
            "spec_dir": spec_dir,
            "story_slug": slug,
        }
    )


# ── recording an outcome ──────────────────────────────────────────────────────────


def _stamp_status(
    logger: logging.Logger, root: Path, epic: str, slug: str, story_path: str
) -> None:
    """Record `QA passed` on the story and commit just that change.

    Deliberately committed SEPARATELY, scoped to the paths the stamp touched, and
    deliberately NOT folded into the caller's `committed` answer. That answer drives the
    zero-diff churn guard (three consecutive no-op story commits halt the run), and a
    status stamp is a change every passing story makes — counting it would mean every story
    always "committed something" and the guard could never trip again.
    """
    written = story_status.mark(root, slug, DONE_STATUS, epic=epic, story_path=story_path, logger=logger)
    if not written:
        logger.warning(
            "status '%s' NOT recorded for %s — it will be re-selected on the next loop",
            DONE_STATUS,
            slug,
        )
        return

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
    repos = resolve_workspace(workspace_file, repo_dir)

    # The epic's sequence number is a folder-ordering device, not part of its name, so the
    # trailer reads `Epic: fixes` whether the caller handed us `fixes` or `0004-fixes`.
    epic_name = registry.epic_slug(epic) or epic
    description = commits.story_description(root, story_path, slug)

    spec = root / spec_dir if spec_dir else None
    plan_ctx = (
        load_json(spec / "plan-context.json", "plan-context.json", logger)
        if spec and spec.exists()
        else {}
    )
    affected = get_affected_repos(plan_ctx, repos)

    # Each repo's commit is scoped to that repo's own name, because that is the name its
    # release-please config knows the package by — one story touching three repos produces
    # three subjects, each releasing the component it actually changed.
    def _story_message(package: str) -> str:
        return commits.message(
            kind, commits.scope(package), description, epic=epic_name, story=slug
        )

    def _commit_in(repo_path: Path, package: str) -> bool:
        """``commit_all``, with a git refusal turned into a halt rather than a False.

        False here flows into the caller's zero-diff counter, and three of them stop the
        run for making no progress. A stale ``index.lock``, a rejecting hook or a failed
        signature is the opposite situation — the story's work exists and git would not
        record it — so it must halt loudly here, while the tree still holds the work and
        the git error is still in hand, rather than be counted as an idle story."""
        try:
            return bool(commit_all(repo_path, _story_message(package)))
        except GitError as exc:
            raise WorkflowFailed(
                f"git refused the commit for {slug} in {repo_path}: {exc}"
            ) from exc

    if not affected:
        # No plan-context.json or no services in it — commit in the resolved root (the
        # single-repo / no-workspace-file case, and test sandboxes with no seeded plan).
        logger.info("no affected repos resolved from plan-context — falling back to the repo root")
        any_committed = _commit_in(root, root.name)
        if any_committed:
            logger.info("committed in %s", root.name)
    else:
        any_committed = False
        for name in affected:
            repo_path = Path(repos.get(name, {}).get("path", ""))
            if not repo_path.is_dir():
                logger.warning("repo %s path not found: %s", name, repo_path)
                continue
            if not (repo_path / ".git").exists():
                logger.warning("repo %s is not a git repo — skipping", name)
                continue
            if _commit_in(repo_path, name):
                logger.info("committed in %s", repo_path.name)
                any_committed = True

    _stamp_status(logger, root, epic, slug, story_path)
    return StoryCommitted(committed=any_committed)


def _record_skip(run_dir: str, slug: str) -> None:
    """Add `slug` to the per-run skip set `select_story` reads."""
    if not run_dir or not slug:
        return
    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    skip_file = path / SKIP_FILE
    existing = skip_file.read_text(encoding="utf-8").splitlines() if skip_file.exists() else []
    if slug not in existing:
        with skip_file.open("a", encoding="utf-8") as f:
            f.write(f"{slug}\n")


@blueprint.node
def flag_qa_failure(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    attempts: str = "?",
    story_path: str = "",
    spec_dir: str = "",
    run_dir: str = "",
    repo_dir: str = "",
) -> QaFlagged:
    """A story failed automated QA after its last rework. Flag it and let the queue go on.

    The epic queue is NOT halted. Instead: the story's current state is committed behind a
    clear marker, so the work is preserved and shows up in the epic PR's diff and commit
    list for the reviewer; the epic PR is commented on where one is already open; and the
    workflow continues to the next story.

    The status stamped here deliberately does NOT say "QA passed": this is a give-up, and
    the status is what a human — and `select_story`'s fallback — reads to judge whether the
    story's work is trustworthy. Dependents of this story stay blocked, because they depend
    on work that did NOT pass. Both selection paths already skip a given-up story without
    needing the text to claim a pass: ostler reads the same honest value out of the
    frontmatter, and the per-run skip set excludes the slug for the rest of THIS run
    regardless of the status text. A fresh run, or an operator clearing the skip set, will
    legitimately retry it.

    It also names `qa.md`, which is the document that says *why*. Everything else the
    give-up leaves behind points somewhere else: the story's own `## Implementation Status`
    block links `review.md` (written by the review phase, about code quality) and nothing
    links the QA assessment, so a reader who does the "manual review" this asks for lands
    on a code review that is silent about the failure. The path goes in the status text
    rather than in a second bullet because the status is the one line this node reliably
    owns — the link bullets are the review prompt's to write, and on this path that prompt
    may never have run.
    """
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)

    marker = f"[QA FAILED after {attempts} attempts — needs manual review]"
    new_status = f"QA give-up after {attempts} attempts — needs manual review"
    assessment = _qa_assessment_path(root, spec_dir)
    if assessment:
        new_status = f"{new_status}: {assessment}"
    story_status.mark(root, slug, new_status, epic=epic, story_path=story_path, logger=logger)

    # Belt-and-braces over the stamp above: this excludes the story for the REMAINDER OF
    # THIS RUN even if the stamp did not take (no graph AND no story.md). The file lives in
    # the run dir, so a fresh run starts with an empty set and an operator resets by
    # clearing it.
    _record_skip(run_dir, slug)

    # Still `feat`: whatever the marker says about its QA, this commit carries the story's
    # implementation, and a reviewer who merges it ships that code. Typing the give-up
    # `chore` to dodge a version bump would ship the feature with no release naming it —
    # the exact silence this format exists to prevent.
    committed = bool(
        commit_all(
            root,
            commits.message(
                "feat",
                commits.scope(root.name),
                slug,
                marker=marker,
                epic=epic,
                story=slug,
            ),
        )
    )
    if not committed:
        logger.info("nothing to commit for %s (no changes, or the commit failed)", slug)

    _comment_on_epic_pr(
        logger,
        root,
        epic,
        slug,
        marker,
        f"did not pass automated QA after {attempts} rework attempts.",
        assessment,
    )
    return QaFlagged(qa_flagged=committed)


@blueprint.node
def flag_docs_block(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    notes: str = "",
    story_path: str = "",
    run_dir: str = "",
    repo_dir: str = "",
) -> DocsBlockFlagged:
    """The docs phase refused the story. Flag it and let the queue go on.

    `flag_qa_failure`'s sibling, for the other verdict that ends a story without finishing
    it. A documentation block is not a documentation bug: it is the author or the reviewer
    saying the book cannot be made true of this code — usually, as the run that forced this
    node found, because the implementation contradicts a guarantee its own plan required.
    That is a real finding about the *story*, and the same three properties that make the QA
    give-up safe make it safe here: the work is committed behind a marker so a human can
    see it, the status is stamped honestly so dependents stay blocked, and the slug joins
    the per-run skip set so the queue moves on instead of re-documenting the same refusal.

    Failing the whole run instead — which is what the flow did before — cost every epic
    behind this one for a finding scoped to one story.

    No assessment path goes in the status the way `qa.md` does for a QA give-up: a docs
    block leaves no document of its own, so `notes` is the only record of why and it goes
    into the status text directly.
    """
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)

    marker = "[DOCS BLOCKED — needs manual review]"
    reason = notes.strip().replace("\n", " ") or "no reason given"
    story_status.mark(
        root,
        slug,
        f"Docs blocked — needs manual review: {reason}",
        epic=epic,
        story_path=story_path,
        logger=logger,
    )
    _record_skip(run_dir, slug)

    # `feat` for the same reason as the QA give-up: the marker qualifies the story, it does
    # not remove the story's code from the commit.
    committed = bool(
        commit_all(
            root,
            commits.message(
                "feat",
                commits.scope(root.name),
                slug,
                marker=marker,
                epic=epic,
                story=slug,
            ),
        )
    )
    if not committed:
        logger.info("nothing to commit for %s (no changes, or the commit failed)", slug)

    _comment_on_epic_pr(
        logger,
        root,
        epic,
        slug,
        marker,
        f"could not be documented — the documentation phase reported it blocked: {reason}",
    )
    return DocsBlockFlagged(docs_block_flagged=committed)


def _qa_assessment_path(root: Path, spec_dir: str) -> str:
    """`<spec_dir>/qa.md` repo-relative, or `""` when there is no such file.

    Existence-checked rather than assumed: a give-up can happen before QA ever wrote an
    assessment (the QA-plan repair budget running out with no plan to execute), and a
    status pointing at a file that is not there is worse than one that points nowhere.
    """
    if not spec_dir:
        return ""
    qa_md = Path(spec_dir) / "qa.md"
    if not qa_md.is_file():
        return ""
    try:
        return str(qa_md.relative_to(root))
    except ValueError:
        return str(qa_md)  # outside the repo — an absolute path still finds it


def _comment_on_epic_pr(
    logger: logging.Logger, root: Path, epic: str, slug: str, marker: str, why: str,
    assessment: str = "",
) -> None:
    """Best-effort note on the epic PR — it only lands if that PR is already open.

    During the story loop it usually is not (the PR is opened after the last story), so the
    marker commit is the reliable signal and this is the convenience.

    `why` is the caller's own sentence about what went wrong, because the two give-ups this
    serves fail for unrelated reasons and a comment that called a docs block a QA failure
    would send the reviewer to the wrong artefact.
    """
    branch = f"feat/{epic}"
    token = resolve_github_token(root)
    if not token:
        return
    repo, _ = resolve_repo(root, token)
    pr = find_open_pr(repo, branch) if repo is not None else None
    if pr is None:
        logger.info(
            "epic PR for %s not open yet — relying on the marker commit to flag %s", branch, slug
        )
        return
    try:
        where = f" The QA assessment is at `{assessment}`." if assessment else ""
        pr.create_issue_comment(
            f"⚠️ Story `{slug}` {why} "
            f"It was committed behind the marker `{marker}` for manual review.{where}",
        )
    except Exception as exc:  # noqa: BLE001 - a PR comment is never worth failing the run
        logger.info("could not post PR comment for %s: %s", slug, exc)


__all__ = [
    "branch_epic",
    "branch_story",
    "commit_story",
    "flag_docs_block",
    "flag_epic_blocked",
    "flag_qa_failure",
    "init_base",
    "prune_epic",
    "select_epic",
    "select_story",
]
