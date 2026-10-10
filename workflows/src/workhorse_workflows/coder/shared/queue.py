"""The main graph's queue spine: which stories a launch files, and the epic it pops when merged."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ostler import Ostler, path as okf_path
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import paths, stubs, work
from workhorse_workflows.coder.shared.branches import CLAIMED_FILE
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.queue import (
    EpicPruned,
    LaunchEntry,
    LaunchSet,
    RunScope,
)

LEGACY_QUEUE_NAME = "epics-todo.json"

ALL_EPICS = "all"


def legacy_queue(root: Path) -> Path:
    """The legacy JSON queue for *root*, beside the ostler-managed `index.md`."""
    return okf_path.epics_root_in(root) / LEGACY_QUEUE_NAME


@blueprint.node
def begin_run(logger: logging.Logger, run_dir: str = "") -> RunScope:
    """Drop the worklist, answer log and branch claims a previous run left in this run dir."""
    if not run_dir:
        return RunScope()
    path = Path(run_dir)
    cleared = []
    for name in (work.WORKLIST_FILE, work.ANSWER_LOG, CLAIMED_FILE):
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


def _queued_epics(root: Path, okf: Ostler) -> list[str]:
    """The epics queue, front-first, from ostler or the legacy JSON file."""
    epics = _queue_from_ostler(okf)
    if not epics:
        epics = _queue_from_json(root) or epics
    if epics is None:
        raise WorkflowFailed("could not read the epics queue (ostler todo list)")
    return epics


def _open_entries(okf: Ostler, epic: str) -> list[dict]:
    try:
        return okf.open_stories(epic)
    except ValueError as exc:
        raise WorkflowFailed(f"epic {epic!r} cannot be launched: {exc}") from exc


@blueprint.node(stub=stubs.launch_set)
def resolve_launch(
    logger: logging.Logger,
    docs_path: str = "",
    epic: str = ALL_EPICS,
    story: str = "",
    repo_dir: str = "",
) -> LaunchSet:
    """Every story this launch works, in order, or a launch error before any turn runs."""
    grain = epic.strip() or ALL_EPICS
    if story and grain != ALL_EPICS:
        raise WorkflowFailed(
            f"the launch names both story={story!r} and epic={epic!r}: name one of them"
        )
    root = find_docs_root(docs_path, repo_dir)
    okf = Ostler(root)
    if story:
        entry = okf.story(story)
        if entry is None:
            raise WorkflowFailed(f"no story {story!r} in the book at {root}")
        logger.info("launch: story %s of epic %s", entry["slug"], entry["epic"])
        return LaunchSet(
            mode="story",
            entries=[LaunchEntry(slug=entry["slug"], id=entry["id"] or "", epic=entry["epic"])],
        )
    epics = _queued_epics(root, okf) if grain == ALL_EPICS else [grain]
    found = [(name, entry) for name in epics for entry in _open_entries(okf, name)]
    launched = {ref for _, entry in found for ref in (entry["slug"], entry["id"]) if ref}
    outside = [
        f"{entry['slug']} needs {dep}"
        for _, entry in found
        for dep in entry.get("open_deps", [])
        if dep not in launched
    ]
    if outside:
        raise WorkflowFailed(
            "the launch depends on stories it does not include: " + "; ".join(outside)
        )
    logger.info("launch: %d open stories across %d epics", len(found), len(epics))
    return LaunchSet(
        mode="epic",
        entries=[
            LaunchEntry(slug=entry["slug"], id=entry["id"] or "", epic=name)
            for name, entry in found
        ],
    )


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


__all__ = [
    "ALL_EPICS",
    "begin_run",
    "prune_epic",
    "resolve_launch",
]
