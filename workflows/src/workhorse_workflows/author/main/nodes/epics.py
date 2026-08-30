"""Which epic the run works on next.

Ported from `base-library/workflows/author/scripts/select-epic.py`.
"""
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
    """Epics in milestone order, used when the legacy todo queue is absent.

    `docs/epics/index.md` is now a compatibility view, not a required authoring artifact.
    A fresh milestone-based run may therefore have no todo list at all; the milestone files are
    the durable sequencing model. If a repo has not adopted milestones yet, fall back to graph
    order so older fixtures and repos still author.
    """
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
    epics_dir: str,
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
        # No index/milestones/epics yet -> the epic-split stage must create them.
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

    # The queue entry may be written as a bare slug while the directory on disk is numbered
    # (`0001-checkout-flow`), so the name the rest of the run carries is the one ostler
    # resolves it to. Every path downstream is built from it.
    epic = Path(okf.epic_path(pick.id)).name or pick.id
    logger.info("selected epic '%s' — %s", epic, selected_reason)
    return EpicChoice(
        has_epic=True,
        epic=epic,
        epic_dir=paths.epic_dir(root, epic, epics_dir),
        reason=selected_reason,
        progress=snap.progress,
    )


@blueprint.node
def select_epic_document(
    logger: logging.Logger,
    epics_dir: str = "",
    repo_dir: str = "",
    roadmap: str = "",
) -> EpicChoice:
    """The first queued epic whose milestone/epic authoring pass is not complete.

    The author workflow runs two epic worklists. This first pass completes every queued
    epic's milestone-level documentation, `epic.md`, and researched seeds before any story bodies
    are written. A rerun resumes at the first epic that still lacks those inputs.
    """
    return _pick_epic(
        logger,
        epics_dir,
        repo_dir,
        roadmap=roadmap,
        done=_epic_documented,
        finished_reason="every epic in the queue has epic docs and researched seeds",
        selected_reason="epic needs epic.md completion or researched seeds",
    )


@blueprint.node
def select_epic(
    logger: logging.Logger,
    epics_dir: str = "",
    repo_dir: str = "",
    roadmap: str = "",
) -> EpicChoice:
    """The first epic in the queue whose authoring is not yet complete.

    **ostler owns the verdict.** `epic_authored` means the epic has an `epic.md`, lists at
    least one story, and every listed story's `story.md` is actually *written* — its
    required sections carry prose. This node must not re-derive that from the filesystem:
    it used to, by testing that each `story.md` merely *existed*, which a bare scaffold
    satisfies, so an epic of 44 empty stories read as fully authored and a rerun ended
    immediately instead of going back to finish the work.

    The queue is a worklist whose *done* items are the authored epics, so `select_next`
    returns the front not-done epic — the front-not-complete rule — and the snapshot gives
    the dashboard its epic progress. `has_epic` false is not a failure; it means the
    backlog is decomposed and the flow moves on to the whole-repo checks.
    """
    return _pick_epic(
        logger,
        epics_dir,
        repo_dir,
        roadmap=roadmap,
        done=lambda okf, epic: okf.epic_authored(epic),
        finished_reason="every epic in the queue is fully authored",
        selected_reason="epic missing stories, or a story is still unwritten",
    )


__all__ = ["select_epic", "select_epic_document"]
