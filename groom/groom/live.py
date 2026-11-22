"""Event-driven fleet push: sources mark the fleet dirty, one coalesced flush sends only the rows and meta that changed, and one timer per run fires when its silence would cross the liveness threshold."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from groom import projection, state
from groom.models import RunTelemetry

logger = logging.getLogger(__name__)

STABLE_EXCLUDED = ("silence_s", "telemetry_age_s", "live_label")
DEADLINE_SLACK_S = 0.5

_loop: asyncio.AbstractEventLoop | None = None
_flush_handle: asyncio.TimerHandle | None = None
_flush_loop: asyncio.AbstractEventLoop | None = None
_deadlines: dict[str, asyncio.TimerHandle] = {}
_sent_rows: dict[str, dict[str, Any]] | None = None
_sent_meta: dict[str, Any] | None = None


def flush_s() -> float:
    return float(os.environ.get("GROOM_FLUSH_S", "0.1"))


def reset() -> None:
    global _loop, _flush_handle, _flush_loop, _sent_rows, _sent_meta
    if _flush_handle is not None:
        _flush_handle.cancel()
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


def mark_fleet() -> None:
    global _flush_handle, _flush_loop
    loop = _running()
    if loop is None:
        return
    if _flush_handle is not None and _flush_loop is loop and not _flush_handle.cancelled():
        return
    _flush_loop = loop
    _flush_handle = loop.call_later(flush_s(), _flush)


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
        _sent_meta = _meta_of(message)
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
    if meta != _sent_meta:
        state.broadcast_nowait({"type": "fleet_meta", "v": _next_v(), **meta})
    _sent_rows = {run_id: stable(row) for run_id, row in current.items()}
    _sent_meta = meta


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
    mark_fleet()
