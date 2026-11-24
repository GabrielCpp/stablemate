"""The main graph's launch: which stories a run files on its own worklist."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit.paths import ostler_for
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import stubs, work
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.queue import (
    LaunchEntry,
    LaunchSet,
    RunScope,
)

ALL_EPICS = "all"


@blueprint.node
def begin_run(logger: logging.Logger, run_dir: str = "") -> RunScope:
    """Drop the worklist and answer log a previous run left in this run dir."""
    if not run_dir:
        return RunScope()
    path = Path(run_dir)
    cleared = []
    for name in (work.WORKLIST_FILE, work.ANSWER_LOG):
        stale = path / name
        if stale.exists():
            stale.unlink()
            cleared.append(name)
    if cleared:
        logger.info("cleared %s left by a previous run in this run dir", ", ".join(cleared))
    return RunScope(cleared=cleared)


def _milestone_epics(root: Path, facade: Ostler) -> list[str]:
    """Every epic the project's milestones list, in the order ostler gives them."""
    epics = facade.milestone_epics()
    if not epics:
        raise WorkflowFailed(f"no milestone in the book at {root} lists an epic")
    unknown = [name for name in epics if facade.graph.epic_by_ref(name) is None]
    if unknown:
        raise WorkflowFailed(
            "a milestone lists an epic the book does not hold: " + ", ".join(unknown)
        )
    return epics


def _open_entries(facade: Ostler, epic: str) -> list[dict]:
    try:
        return facade.open_stories(epic)
    except ValueError as exc:
        raise WorkflowFailed(f"epic {epic!r} cannot be launched: {exc}") from exc


@blueprint.node(stub=stubs.launch_set)
def resolve_launch(
    logger: logging.Logger,
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
    root = find_docs_root(repo_dir)
    facade = ostler_for(repo_dir)
    if story:
        entry = facade.story(story)
        if entry is None:
            slugged = facade.graph.story_by_slug(story)
            if slugged is not None and slugged[1].eid:
                entry = facade.story(slugged[1].eid)
        if entry is None:
            raise WorkflowFailed(f"no story {story!r} in the book at {root}")
        logger.info("launch: story %s of epic %s", entry["slug"], entry["epic"])
        return LaunchSet(
            mode="story",
            entries=[LaunchEntry(slug=entry["slug"], id=entry["id"] or "", epic=entry["epic"])],
        )
    epics = _milestone_epics(root, facade) if grain == ALL_EPICS else [grain]
    found = [(name, entry) for name in epics for entry in _open_entries(facade, name)]
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


__all__ = [
    "ALL_EPICS",
    "begin_run",
    "resolve_launch",
]
