from __future__ import annotations

import asyncio
import logging
import os

from groom import (
    history,
    live,
    pools,
    state,
    tasks,
)

logger = logging.getLogger(__name__)



SUMMARY_EVERY_S = float(os.environ.get("GROOM_SUMMARY_EVERY_S", "60"))


SUMMARY_PAUSE_S = float(os.environ.get("GROOM_SUMMARY_PAUSE_S", "0.25"))


_summary_wake: asyncio.Event | None = None


_summary_task: asyncio.Task | None = None


def _wake_summaries() -> None:
    if _summary_wake is not None:
        _summary_wake.set()


async def _write_summary(run_id: str) -> None:
    """Write one run's summary, then tell every tab it is there so an open Overview and the History list read it."""
    await pools.SUMMARY.run(history.compute, run_id)
    await state.broadcast({"type": "summary", "run_id": run_id})
    live.bump("history")


async def _summary_pass() -> int:
    """Find the ended runs with no current summary and write them one at a time, pausing between runs so the event loop and the store serve the dashboard first. Archives that stored no summary follow, one at a time, and give way as soon as another run needs one."""
    wanted = await pools.SUMMARY.run(history.discover)
    if wanted:
        live.bump("history")
    for run_id in wanted:
        await _write_summary(run_id)
        await asyncio.sleep(SUMMARY_PAUSE_S)
    older = await pools.SUMMARY.run(history.discover_archives)
    if older:
        live.bump("history")
    for run_id in older:
        if _summary_wake is not None and _summary_wake.is_set():
            break
        await pools.ARCHIVE.run(history.compute_archive, run_id)
        live.bump("history")
        await asyncio.sleep(SUMMARY_PAUSE_S)
    return len(wanted) + len(older)


async def _summary_loop() -> None:
    """Fill the run summaries on a slow clock, and at once when a run ends."""
    global _summary_wake
    wake = _summary_wake = asyncio.Event()
    wake.set()
    try:
        while True:
            try:
                await asyncio.wait_for(wake.wait(), SUMMARY_EVERY_S)
            except TimeoutError:
                pass
            wake.clear()
            try:
                await _summary_pass()
            except Exception:  # noqa: BLE001
                logger.warning("groom: run summaries could not be written", exc_info=True)
    finally:
        if _summary_wake is wake:
            _summary_wake = None


async def _spawn_summaries() -> None:
    """on_startup hook: start the worker that writes run summaries."""
    global _summary_task
    _summary_task = tasks.spawn(_summary_loop(), name="summaries")


async def _stop_summaries() -> None:
    if _summary_task is not None:
        _summary_task.cancel()
