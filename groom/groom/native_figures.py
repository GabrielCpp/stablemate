from __future__ import annotations

import asyncio
import logging

from groom import (
    figures,
    live,
    norms,
    pools,
    projection,
    state,
    tasks,
)
from groom.models import (
    WorkflowContainer,
)

logger = logging.getLogger(__name__)



def _figures_rev(wf: WorkflowContainer) -> int:
    """How many span batches the watched run has absorbed plus how many cached norms of its workflow changed after their first read, so a pane knows when its Overview figures are stale."""
    run_id = projection.run_id_of(wf)
    history = state.HISTORIES.get(run_id)
    workflow = projection.run_workflow(wf, state.RUNS.get(run_id))
    return (history.revision if history is not None else 0) + norms.revision(workflow)


_FIGURES_RUNNING: set[str] = set()


_FIGURES_DIRTY: set[str] = set()


_FIGURES_TASKS: set[asyncio.Task] = set()


async def _refresh_figures(run_id: str) -> None:
    """Recompute one run's row figures through the query pool, with at most one pass running per run and one rerun queued behind it."""
    if run_id in _FIGURES_RUNNING:
        _FIGURES_DIRTY.add(run_id)
        return
    _FIGURES_RUNNING.add(run_id)
    try:
        while True:
            _FIGURES_DIRTY.discard(run_id)
            try:
                computed = await pools.QUERY.run(figures.run_figures, run_id)
            except Exception:
                logger.warning("row figures for %s could not be read", run_id, exc_info=True)
            else:
                run = state.RUNS.get(run_id)
                if run is not None and run.figures != computed:
                    run.figures = computed
                    live.mark_fleet()
            if run_id not in _FIGURES_DIRTY:
                return
    finally:
        _FIGURES_RUNNING.discard(run_id)


def _schedule_figures(records: list, *, stale: bool) -> None:
    """After a committed batch, refresh the figures of the runs it touched; ``stale`` False refreshes only runs that have none yet."""
    for run_id in {r.get("run_id") for r in records if r.get("run_id")}:
        run = state.RUNS.get(run_id)
        if run is None or (not stale and run.figures is not None):
            continue
        task = tasks.spawn(_refresh_figures(run_id), name="refresh-figures")
        _FIGURES_TASKS.add(task)
        task.add_done_callback(_FIGURES_TASKS.discard)
