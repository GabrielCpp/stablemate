"""The main graph's queue spine: pick an epic, pick a story, branch, record the outcome."""
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

LEGACY_QUEUE_NAME = "epics-todo.json"


def legacy_queue(root: Path) -> Path:
    """The legacy JSON queue for *root*, beside the ostler-managed `index.md`."""
    return okf_path.epics_root_in(root) / LEGACY_QUEUE_NAME


def _has_queue_bullet(content: str) -> bool:
    """Whether *content* holds at least one `- [epic](…)` queue entry."""
    return any(b.bracketed[0] for b in markdown.split(content).walk_bullets())


BLOCKED_FILE = "blocked-epics.txt"

SKIP_FILE = "qa-skip-stories.txt"

CLAIMED_FILE = "epic-branches.txt"

DONE_STATUS = "QA passed"




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
    """Drop the skip state a previous run left behind in this run dir."""
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
    """Resolve the branch an epic's PR will be opened against, before anything is cut."""
    root = find_repo_root(repo_dir)
    base = active_branch(root)
    if not base or base.startswith("feat/") or base.startswith("rewrite/"):
        base = _resolve_trunk(root)
    logger.info("base branch is '%s'", base)
    return BaseBranch(base_branch=base)


def _branch_repo(logger: logging.Logger, repo_path: Path, repo_name: str, branch: str) -> bool:
    """Cut or check out `branch` in one repo."""
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
    """Cut the working branch for a single story, in the docs repo and every affected repo."""
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
            continue
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
    """Put this run on `feat/<epic>`, or refuse and say why."""
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
    """`base` as it resolves in this repo — the local branch, else `origin/<base>`, else ""."""
    if not base:
        return ""
    for ref in (base, f"origin/{base}") if "/" not in base else (base,):
        if branch_exists(root, ref):
            return ref
    return ""


def _catch_up_with_base(logger: logging.Logger, root: Path, branch: str, base: str) -> None:
    """Bring `base` into an epic branch this run cut before `base` moved on without it."""
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
    """Restore the epic queue from `base`, when `base` has an authoritative copy of it."""
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
    """Put this run on `feat/<epic>`, cutting it from HEAD when it does not exist yet."""
    root = find_repo_root(repo_dir)
    restore_paths(root, paths.epics_index(root))

    if epic:
        _claim_epic_branch(logger, root, f"feat/{epic}", base_branch, run_dir.strip())

    _reconcile_queue(logger, root, base_branch)
    return EpicBranch(working_epic=epic, epic_branch=f"feat/{epic}")




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
    """Epics set aside THIS run by `flag_epic_blocked`."""
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
    """Return the front epic of the queue that has not been set aside this run."""
    root = find_docs_root(docs_path, repo_dir)
    okf = Ostler(root)

    epics = _queue_from_ostler(okf)
    if epics is None or (not epics and _queue_from_json(root) is not None):
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
    """Set a blocked epic aside for the rest of this run, and report the whole set."""
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
    logger.warning("%s", reason)
    return EpicBlocked(epic_blocked=True, blocked_epics=",".join(blocked), reason=reason)


def _record_blocked(run_dir: str, epic: str) -> list[str]:
    """Append `epic` to the per-run blocked set and return the whole set, in order."""
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
    epics.remove(epic)
    try:
        todo_path.write_text(json.dumps(epics, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


@blueprint.node
def prune_epic(
    logger: logging.Logger, epic: str = "", todo_path: str = "", repo_dir: str = ""
) -> EpicPruned:
    """Pop a merged epic off the front of the queue."""
    if not epic:
        logger.info("no epic given — nothing to prune")
        return EpicPruned()

    root = paths.epics_repo_root(repo_dir)

    if todo_path.strip():
        sidecar = Path(todo_path.strip())
        if not sidecar.is_absolute():
            sidecar = root / sidecar
        logger.info("explicit sidecar %s given — pruning '%s' from it", sidecar, epic)
        return EpicPruned(pruned=_prune_json_sidecar(sidecar, epic))

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




def _progress_fields(report: dict | str) -> tuple[str, int]:
    """Queue progress for the dashboard, through the shared worklist snapshot."""
    if not isinstance(report, dict):
        return "", 0
    done = int(report.get("done") or 0)
    remaining = [str(s) for s in (report.get("remaining") or [])]
    items = [wl.WorkItem(id=f"__done_{i}", status="done") for i in range(done)]
    items += [wl.WorkItem(id=s, status="pending") for s in remaining]
    snap = wl.snapshot(items)
    return snap.progress, snap.remaining


def _next_story_report(okf: Ostler, epic: str, skip: set[str]) -> dict | str:
    """Ostler's next-story report, or `""` on a tooling failure."""
    try:
        return okf.next_story_report(epic, skip=skip)
    except (OSError, ValueError, RuntimeError):
        return ""


def _load_skip_set(root: Path, run_dir: str) -> set[str]:
    """The per-run skip set: story slugs to leave alone for the REST OF THIS RUN."""
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
    """Select the next runnable story within `epic`, or say why there is none."""
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

    fields: dict = report if isinstance(report, dict) else {}
    state = fields.get("state", "")
    nxt = fields.get("story")

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
            "story_id": str(nxt.get("id") or ""),
        }
    )




def _stamp_status(
    logger: logging.Logger, root: Path, epic: str, slug: str, story_path: str
) -> tuple[bool, bool]:
    """Record `QA passed` on the story and commit just that change."""
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

    specs: list[str] = []
    for path in written:
        try:
            specs.append(str(path.resolve().relative_to(root.resolve())))
        except ValueError:
            logger.info("status file %s is outside %s — not committing it here", path, root)
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
    """Which checkouts this story's commit covers — the caller's list, or the plan's."""
    if roots:
        return [(Path(p).name, Path(p)) for p in roots]
    return _affected_roots(logger, root, spec_dir, workspace_file, repo_dir)


def _affected_roots(
    logger: logging.Logger, root: Path, spec_dir: str, workspace_file: str, repo_dir: str
) -> list[tuple[str, Path]]:
    """The repos this story's plan says it touched, as `(package name, checkout)` pairs."""
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
    """Every path in *root* holding work that is not in a commit yet."""
    try:
        repo = open_repo(root)
        dirty = {item.a_path for item in repo.index.diff(None) if item.a_path}
        dirty |= set(repo.untracked_files)
        try:
            dirty |= {item.a_path for item in repo.index.diff("HEAD") if item.a_path}
        except (GitError, OSError, TypeError, ValueError, KeyError):
            pass
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
    """Did the agent commit its own work in every repo the story touched?"""
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
    """Record the story's passing outcome, and commit that one line."""
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
    story_id: str = "",
) -> StoryCommitted:
    """Commit a completed story's changes in each affected code repo, then stamp it passed."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)

    epic_name = registry.epic_slug(epic) or epic
    description = commits.story_description(root, story_path, slug)

    def _story_message(package: str) -> str:
        return commits.message(
            kind, commits.scope(package), description, epic=epic_name, story=story_id or slug
        )

    def _commit_in(repo_path: Path, package: str) -> bool:
        """``commit_all``, with a git refusal turned into a halt rather than a False."""
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
