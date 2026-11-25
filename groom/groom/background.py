from __future__ import annotations

import asyncio
import logging
import os
import time

from groom import (
    alerting,
    alerts,
    archive,
    attend,
    dispatch,
    live,
    native,
    state,
    store,
    tasks,
    turns,
)

logger = logging.getLogger(__name__)


RULES_TICK_S = float(os.environ.get("GROOM_RULES_TICK_S", "60"))


PRUNE_EVERY_S = float(os.environ.get("GROOM_PRUNE_EVERY_S", "3600"))


HARVEST_EVERY_S = float(os.environ.get("GROOM_HARVEST_EVERY_S", "300"))


ARCHIVE_EVERY_S = archive.ARCHIVE_EVERY_S


_scan_task: asyncio.Task | None = None


_rules_task: asyncio.Task | None = None


_heartbeat_task: asyncio.Task | None = None


_archive_task: asyncio.Task | None = None


async def _rules_loop() -> None:
    """Periodic evaluation of the time-based alert rules, plus the two housekeeping passes that bound groom's memory over a long serve: evicting finished/dead runs from the hot cache, and re-pruning the durable store on its own slower clock."""
    last_prune = time.monotonic() - PRUNE_EVERY_S
    last_harvest = time.monotonic()
    while True:
        await asyncio.sleep(RULES_TICK_S)
        try:
            now = time.time()
            await alerting._dispatch_alerts(alerts.check_time_rules(now))
            state.evict_runs(alerts.stale_run_ids(now))
            live.mark_fleet()
            if time.monotonic() - last_harvest >= HARVEST_EVERY_S:
                await asyncio.to_thread(turns.harvest)
                last_harvest = time.monotonic()
            if time.monotonic() - last_prune >= PRUNE_EVERY_S:
                archived = await asyncio.to_thread(archive.archived_run_ids)
                await asyncio.to_thread(store.prune, store.RETENTION_DAYS, None, archived)
                last_prune = time.monotonic()
        except Exception:  # noqa: BLE001
            logger.exception("groom: alert rules tick failed")


async def _bind_live() -> None:
    """on_startup hook: bind the push flush to this loop and hand it the detail builder."""
    live.bind(asyncio.get_running_loop())
    state.WATCH_REFRESH = live.resend_detail


def heartbeat_s() -> float:
    return float(os.environ.get("GROOM_HEARTBEAT_S", "5"))


async def _heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(heartbeat_s())
        try:
            state.broadcast_nowait({"type": "ping"})
        except Exception:  # noqa: BLE001
            logger.warning("groom: heartbeat failed", exc_info=True)


async def _spawn_heartbeat() -> None:
    """on_startup hook: start the ping that keeps an idle dashboard socket from reading stale."""
    global _heartbeat_task
    _heartbeat_task = tasks.spawn(_heartbeat_loop(), name="heartbeat")


async def _stop_heartbeat() -> None:
    if _heartbeat_task is not None:
        _heartbeat_task.cancel()


async def _bind_history_lock() -> None:
    """on_startup hook: give the loop that serves this app a history lock of its own, because a lock binds to the first loop that waits on it."""
    state.HISTORY_LOCK = asyncio.Lock()


async def _archive_loop() -> None:
    """Write expired runs out to disk on a slow clock, forever."""
    last = time.monotonic() - ARCHIVE_EVERY_S
    while True:
        await asyncio.sleep(RULES_TICK_S)
        if time.monotonic() - last < ARCHIVE_EVERY_S:
            continue
        last = time.monotonic()
        try:
            result = await asyncio.to_thread(archive.sweep)
            if result.archived or result.failed:
                logger.info(
                    "groom: archived %d run(s), %d row(s), %d byte(s); %d failed,"
                    " %d still pending",
                    len(result.archived), result.rows, result.bytes,
                    len(result.failed), result.pending,
                )
        except Exception:  # noqa: BLE001
            logger.warning("groom: archival sweep failed", exc_info=True)


async def _spawn_archive() -> None:
    """on_startup hook: start the archival ticker."""
    global _archive_task
    _archive_task = tasks.spawn(_archive_loop(), name="archive")


async def _stop_archive() -> None:
    if _archive_task is not None:
        _archive_task.cancel()


async def _spawn_rules() -> None:
    """on_startup hook: start the alert-rule ticker, and nothing else."""
    global _rules_task
    _rules_task = tasks.spawn(_rules_loop(), name="alert-rules")


async def _stop_rules() -> None:
    if _rules_task is not None:
        _rules_task.cancel()


async def _background_scan() -> None:
    """The startup discovery pass, run off the event loop *after* the server is already accepting connections."""
    try:
        await native._reconcile()
    finally:
        state.SCANNING = False
        live.mark_fleet()


async def _recover_attend() -> None:
    """on_startup hook: restart the attendants this groom was holding when it died."""
    try:
        restarted = await asyncio.to_thread(attend.recover_orphans)
    except Exception:
        logger.exception("attend: boot recovery failed")
        return
    if restarted:
        logger.info("attend: restarted %d attendant(s) left running by a dead groom", restarted)


async def _recover_dispatch() -> None:
    """on_startup hook: mark every `running` dispatch row dead pids own as `failed`."""
    try:
        closed = await asyncio.to_thread(dispatch.recover_orphans)
    except Exception:
        logger.exception("dispatch: boot recovery failed")
        return
    if closed:
        logger.info("dispatch: marked %d orphaned item(s) failed after a dead groom", closed)


async def _spawn_scan() -> None:
    """on_startup hook: only *schedule* discovery and return immediately, so uvicorn finishes lifespan-startup and binds the port right away instead of blocking on the whole docker scan (the old _startup_scan did the latter)."""
    global _scan_task
    _scan_task = tasks.spawn(_background_scan(), name="discovery-scan")
