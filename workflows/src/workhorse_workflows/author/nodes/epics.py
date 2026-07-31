"""Which epic the run works on next.

Ported from `base-library/workflows/author/scripts/select-epic.py`.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler
from workhorse import worklist as wl
from workhorse_workflows.author.nodes._blueprint import blueprint
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import EpicChoice


@blueprint.node
def select_epic(
    logger: logging.Logger, epics_dir: str = "", repo_dir: str = ""
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
    root = survey_repo_root(repo_dir)
    okf = Ostler(root)

    try:
        queue = okf.todo()
    except (OSError, ValueError, RuntimeError):
        reason = "could not read the epics queue via `ostler todo list`"
        logger.warning(reason)
        return EpicChoice(reason=reason)

    if not queue:
        # No index yet → the epic-split stage must create the epics and queue them.
        reason = "epics queue is empty — the epic-split stage must create + queue epics"
        logger.info(reason)
        return EpicChoice(reason=reason)

    # Items stay in queue order (no `order` key → sequence order preserved).
    items = [
        wl.WorkItem(
            id=str(epic), status="done" if okf.epic_authored(str(epic)) else "pending"
        )
        for epic in queue
    ]

    snap = wl.snapshot(items)
    pick = wl.select_next(items)
    if pick is None:
        reason = "every epic in the queue is fully authored"
        logger.info(reason)
        return EpicChoice(reason=reason, progress=snap.progress)

    # The queue entry may be written as a bare slug while the directory on disk is numbered
    # (`0001-checkout-flow`), so the name the rest of the run carries is the one ostler
    # resolves it to. Every path downstream is built from it.
    epic = Path(okf.epic_path(pick.id)).name or pick.id
    logger.info(
        "selected epic '%s' — missing epic.md, has no stories, or a story is unwritten", epic
    )
    return EpicChoice(
        has_epic=True,
        epic=epic,
        epic_dir=paths.epic_dir(root, epic, epics_dir),
        reason="epic missing epic.md, has no stories, or a story is still unwritten",
        progress=snap.progress,
    )


__all__ = ["select_epic"]
