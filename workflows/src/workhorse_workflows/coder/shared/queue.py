"""The main graph's queue spine: which epic and story run next, and what is set aside."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ostler import Ostler, path as okf_path
from workhorse import worklist as wl
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared.branches import CLAIMED_FILE
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.queue import (
    EpicBlocked,
    EpicPick,
    EpicPruned,
    RunScope,
    StoryPick,
)

LEGACY_QUEUE_NAME = "epics-todo.json"


def legacy_queue(root: Path) -> Path:
    """The legacy JSON queue for *root*, beside the ostler-managed `index.md`."""
    return okf_path.epics_root_in(root) / LEGACY_QUEUE_NAME


BLOCKED_FILE = "blocked-epics.txt"

SKIP_FILE = "qa-skip-stories.txt"


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


__all__ = [
    "flag_epic_blocked",
    "prune_epic",
    "select_epic",
    "select_story",
]
