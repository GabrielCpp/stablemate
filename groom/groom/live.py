"""Event-driven push: sources mark the fleet and the runs they touched dirty, one coalesced flush sends the rows and meta that changed and then the open runs' details that changed, and one timer per run fires when its silence would cross the liveness threshold."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from groom import projection, state
from groom.models import RunTelemetry, WorkflowContainer

logger = logging.getLogger(__name__)

STABLE_EXCLUDED = ("silence_s", "telemetry_age_s", "live_label", "last_seen_ts")
STORE_UNSTABLE = ("last_ok_ts", "last_write_ts", "last_prune_ts", "wal_bytes")
DEADLINE_SLACK_S = 0.5

_loop: asyncio.AbstractEventLoop | None = None
_flush_handle: asyncio.TimerHandle | None = None
_flush_loop: asyncio.AbstractEventLoop | None = None
_deadlines: dict[str, asyncio.TimerHandle] = {}
_sent_rows: dict[str, dict[str, Any]] | None = None
_sent_meta: dict[str, Any] | None = None
_detail_builder: Callable[[WorkflowContainer], Awaitable[dict[str, Any]]] | None = None
_dirty_runs: set[str] = set()
_backlog: set[str] = set()
_sent_details: dict[str, dict[str, Any]] = {}
_detail_task: asyncio.Task | None = None


def flush_s() -> float:
    return float(os.environ.get("GROOM_FLUSH_S", "0.1"))


def use_detail_builder(builder: Callable[[WorkflowContainer], Awaitable[dict[str, Any]]]) -> None:
    global _detail_builder
    _detail_builder = builder


def reset() -> None:
    global _loop, _flush_handle, _flush_loop, _sent_rows, _sent_meta, _detail_task
    if _flush_handle is not None:
        _flush_handle.cancel()
    if _detail_task is not None:
        _detail_task.cancel()
    _detail_task = None
    _dirty_runs.clear()
    _backlog.clear()
    _sent_details.clear()
    for handle in _deadlines.values():
        handle.cancel()
    _deadlines.clear()
    _loop = None
    _flush_handle = None
    _flush_loop = None
    _sent_rows = None
    _sent_meta = None
    state.FLEET_V = 0


def bind(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def _running() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def stable(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in STABLE_EXCLUDED}


def stable_meta(meta: dict[str, Any]) -> dict[str, Any]:
    store = {key: value for key, value in meta["store"].items() if key not in STORE_UNSTABLE}
    return {**meta, "store": store}


def mark_fleet() -> None:
    global _flush_handle, _flush_loop
    loop = _running()
    if loop is None:
        return
    if _flush_handle is not None and _flush_loop is loop and not _flush_handle.cancelled():
        return
    _flush_loop = loop
    _flush_handle = loop.call_later(flush_s(), _flush)


def mark_run(run_id: str) -> None:
    """Note that a run's detail may have changed. A run nobody watches is skipped, because a tab that opens it later asks for its detail then."""
    if not state.watchers_of(run_id):
        return
    _dirty_runs.add(run_id)
    mark_fleet()


async def open_detail(queue: asyncio.Queue, run_id: str) -> None:
    """A tab just opened a run: it gets one detail at once, whatever the other tabs already hold, and they get it only when it differs from theirs."""
    wf = state.WORKFLOWS.get(run_id)
    if wf is None or _detail_builder is None:
        return
    message = await _detail_builder(wf)
    state.offer(queue, message)
    detail = message["detail"]
    if _sent_details.get(run_id) == detail:
        return
    _sent_details[run_id] = detail
    for other in state.watchers_of(run_id):
        if other is not queue:
            state.offer(other, message)


def resend_detail(run_id: str) -> None:
    """Every tab watching the run gets its detail again."""
    _sent_details.pop(run_id, None)
    mark_run(run_id)


def release_unwatched() -> None:
    watched = state.watched_ids()
    for run_id in [run_id for run_id in _sent_details if run_id not in watched]:
        del _sent_details[run_id]
    _dirty_runs.intersection_update(watched)
    _backlog.intersection_update(watched)


def mark_fleet_threadsafe() -> None:
    loop = _loop
    if loop is None or loop.is_closed():
        return
    try:
        loop.call_soon_threadsafe(mark_fleet)
    except RuntimeError:
        return


def _workflows() -> list:
    return list(state.WORKFLOWS.values())


def _next_v() -> int:
    state.FLEET_V += 1
    return state.FLEET_V


def snapshot() -> dict[str, Any]:
    """The whole fleet as one ``state`` frame at the current version, and the baseline the next flush diffs against when none exists yet."""
    global _sent_rows, _sent_meta
    message = projection.state_message(_workflows())
    if _sent_rows is None:
        _sent_rows = {row["id"]: stable(row) for row in message["runs"]}
        _sent_meta = stable_meta(_meta_of(message))
    return message


def _meta_of(message: dict[str, Any]) -> dict[str, Any]:
    return {key: message[key] for key in ("scanning", "attention", "status", "store", "attend")}


def _flush() -> None:
    global _flush_handle
    _flush_handle = None
    try:
        flush_fleet()
    except Exception:  # noqa: BLE001 - a missed flush must not stop the next one
        logger.warning("groom: fleet flush failed", exc_info=True)
    _start_details()


def _start_details() -> None:
    global _detail_task
    _backlog.update(_dirty_runs)
    _dirty_runs.clear()
    if not _backlog or (_detail_task is not None and not _detail_task.done()):
        return
    loop = _running()
    if loop is None:
        return
    _detail_task = loop.create_task(_drain_details())


async def _drain_details() -> None:
    while _backlog:
        run_id = _backlog.pop()
        try:
            await _send_detail(run_id)
        except Exception:  # noqa: BLE001 - one run's failed detail must not stop the others
            logger.warning("groom: detail flush failed for %s", run_id, exc_info=True)


async def _send_detail(run_id: str) -> None:
    if not state.watchers_of(run_id):
        _sent_details.pop(run_id, None)
        return
    wf = state.WORKFLOWS.get(run_id)
    if wf is None or _detail_builder is None:
        return
    message = await _detail_builder(wf)
    watchers = state.watchers_of(run_id)
    if not watchers:
        return
    detail = message["detail"]
    changed = _sent_details.get(run_id) != detail
    _sent_details[run_id] = detail
    if changed:
        for queue in watchers:
            state.offer(queue, message)


def flush_fleet() -> None:
    global _sent_rows, _sent_meta
    if not state.CLIENTS:
        _sent_rows = None
        _sent_meta = None
        return
    workflows = _workflows()
    now = time.time()
    rows = projection.fleet_rows(workflows, now=now)
    meta = projection.fleet_meta(workflows)
    previous_rows = _sent_rows if _sent_rows is not None else {}
    current = {row["id"]: row for row in rows}
    for run_id in previous_rows:
        if run_id not in current:
            state.broadcast_nowait({"type": "run_removed", "v": _next_v(), "id": run_id})
    for run_id, row in current.items():
        if previous_rows.get(run_id) != stable(row):
            state.broadcast_nowait({"type": "run", "v": _next_v(), "run": row})
    stable_form = stable_meta(meta)
    if stable_form != _sent_meta:
        state.broadcast_nowait({"type": "fleet_meta", "v": _next_v(), **meta})
    _sent_rows = {run_id: stable(row) for run_id, row in current.items()}
    _sent_meta = stable_form


def _deadline_of(run: RunTelemetry) -> float:
    return projection.last_seen_of(run) + projection.LIVE_AFTER_S + DEADLINE_SLACK_S


def cancel_liveness(run_id: str) -> None:
    handle = _deadlines.pop(run_id, None)
    if handle is not None:
        handle.cancel()


def schedule_liveness(run: RunTelemetry) -> None:
    loop = _running()
    if loop is None:
        return
    cancel_liveness(run.run_id)
    if run.terminal:
        return
    delay = max(0.0, _deadline_of(run) - time.time())
    _deadlines[run.run_id] = loop.call_later(delay, _liveness_due, run.run_id)


def _liveness_due(run_id: str) -> None:
    _deadlines.pop(run_id, None)
    run = state.RUNS.get(run_id)
    if run is None or run.terminal:
        return
    if _deadline_of(run) > time.time():
        schedule_liveness(run)
        return
    mark_run(run_id)
    mark_fleet()
