"""Which epic the run works on next."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from ostler import Ostler
from ostler.select import epic_by_name
from workhorse import worklist as wl
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import EpicChoice


def _milestone_ordered_epics(okf: Ostler) -> list[str]:
    """Epics in milestone order, used when the legacy todo queue is absent."""
    ordered: list[str] = []
    seen: set[str] = set()
    for milestone in okf.graph.milestones:
        for epic in milestone.epics:
            slug = str(epic).strip()
            if slug and slug not in seen:
                ordered.append(slug)
                seen.add(slug)
    if ordered:
        return ordered
    return [epic.name for epic in okf.graph.epics]


def _roadmap_ordered_epics(okf: Ostler, roadmap: str) -> list[str]:
    """The ordered epic worklist owned by one roadmap-sourced milestone."""
    matches = [
        milestone
        for milestone in okf.graph.milestones
        if roadmap in milestone.source_items
    ]
    if len(matches) != 1:
        raise ValueError(
            f"roadmap '{roadmap}' must source exactly one milestone; found {len(matches)}"
        )
    return [str(epic).strip() for epic in matches[0].epics if str(epic).strip()]


def _epic_documented(okf: Ostler, epic: str) -> bool:
    """Whether the epic-level pass has produced this epic's durable authoring inputs."""
    found = epic_by_name(okf.graph, epic)
    return found is not None and found.epic_md is not None and bool(found.seeds)


def _pick_epic(
    logger: logging.Logger,
    repo_dir: str,
    *,
    roadmap: str,
    done: Callable[[Ostler, str], bool],
    finished_reason: str,
    selected_reason: str,
) -> EpicChoice:
    root = survey_repo_root(repo_dir)
    okf = Ostler(root)

    try:
        queue = (
            _roadmap_ordered_epics(okf, roadmap)
            if roadmap
            else okf.todo() or _milestone_ordered_epics(okf)
        )
    except (OSError, ValueError, RuntimeError) as exc:
        reason = f"could not read the epic worklist via ostler: {exc}"
        logger.warning(reason)
        return EpicChoice(reason=reason)

    if not queue:
        reason = "no epics found — the epic-split stage must create milestones and epics"
        logger.info(reason)
        return EpicChoice(reason=reason)

    items = [
        wl.WorkItem(id=str(epic), status="done" if done(okf, str(epic)) else "pending")
        for epic in queue
    ]

    snap = wl.snapshot(items)
    pick = wl.select_next(items)
    if pick is None:
        logger.info(finished_reason)
        return EpicChoice(reason=finished_reason, progress=snap.progress)

    epic = Path(okf.epic_path(pick.id)).name or pick.id
    logger.info("selected epic '%s' — %s", epic, selected_reason)
    return EpicChoice(
        has_epic=True,
        epic=epic,
        epic_dir=paths.epic_dir(root, epic),
        reason=selected_reason,
        progress=snap.progress,
    )


@blueprint.node
def select_epic_document(
    logger: logging.Logger,
    repo_dir: str = "",
    roadmap: str = "",
) -> EpicChoice:
    """The first queued epic whose milestone/epic authoring pass is not complete."""
    return _pick_epic(
        logger,
        repo_dir,
        roadmap=roadmap,
        done=_epic_documented,
        finished_reason="every epic in the queue has epic docs and researched seeds",
        selected_reason="epic needs epic.md completion or researched seeds",
    )


@blueprint.node
def select_epic(
    logger: logging.Logger,
    repo_dir: str = "",
    roadmap: str = "",
) -> EpicChoice:
    """The first epic in the queue whose authoring is not yet complete."""
    return _pick_epic(
        logger,
        repo_dir,
        roadmap=roadmap,
        done=lambda okf, epic: okf.epic_authored(epic),
        finished_reason="every epic in the queue is fully authored",
        selected_reason="epic missing stories, or a story is still unwritten",
    )


__all__ = ["select_epic", "select_epic_document"]
