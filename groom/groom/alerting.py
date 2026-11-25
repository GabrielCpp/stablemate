from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from groom import (
    alerts,
    attend,
    notify,
    projection,
    state,
)
from groom.attention import (
    RULE_EVENTS,
    AttentionEvent,
    AttentionFrame,
)
from groom.summaries import _wake_summaries
from workhorse import reload as reload_mod

logger = logging.getLogger(__name__)


_QUESTION_NOTIFY_LIMIT = 200


async def _broadcast_notify(message: str, rule: str = "", failed: bool = False) -> None:
    """A one-shot alert for the tabs to toast (and raise a browser notification for), naming the alert rule that raised it and, for an ended run, whether it failed."""
    frame: dict[str, Any] = {"type": "notify", "message": message}
    if rule:
        frame["rule"] = rule
    if rule == "ENDED":
        frame["failed"] = failed
    await state.broadcast(frame)


_NOT_A_DEATH_EXIT = frozenset({0, reload_mod.RELOAD_EXIT_CODE})


_NOT_A_DEATH_TERMINAL = frozenset(alerts.CLEAN_TERMINALS) | {"interrupted", "reload"}


def _attend_death(container_id: str) -> None:
    """Put an attendant on a run that ended without reaching its own end."""
    wf = state.WORKFLOWS.get(container_id)
    if wf is None or not wf.native:
        return
    try:
        attend.attend_death(
            run_id=wf.container_id,
            workflow=wf.workflow_type or wf.name,
            run_dir=wf.runs_volume,
            workspace=wf.workspace_volume,
        )
    except Exception:
        logger.exception("attend: dead-run dispatch failed for %s", container_id)


async def _dispatch_alerts(fired: list[alerts.Alert]) -> None:
    """Fan one batch of newly-fired alerts out to every channel: the activity log, the AFK push (ntfy/webhook, off the event loop — urllib blocks), and the browser notification path blocked-gates already use."""
    for alert in fired:
        telemetry = state.RUNS.get(alert.run_id)
        event = AttentionEvent(
            run_id=alert.run_id, event=RULE_EVENTS[alert.rule], message=alert.message,
            node=telemetry.current_node if telemetry else "",
            question=telemetry.wait_gate_question if telemetry else "",
            gate_path=telemetry.wait_gate_path if telemetry else "",
            terminal=telemetry.terminal if telemetry else "",
        )
        now = time.time()
        state.record_event(alert.run_id, event, now)
        for feed in state.feeds_of(alert.run_id):
            _feed_put(feed, event, now)
        await state.broadcast(AttentionFrame(events=[event]).model_dump())
        state.record_log(
            {"event": "alert", "rule": alert.rule, "run_id": alert.run_id, "message": alert.message}
        )
        if alert.rule == "ENDED" and (run := state.RUNS.get(alert.run_id)) is not None and run.terminal != "reload":
            _wake_summaries()
        if alert.rule == "DIED" or (
            alert.rule == "ENDED"
            and (run := state.RUNS.get(alert.run_id)) is not None
            and run.terminal not in _NOT_A_DEATH_TERMINAL
        ):
            _attend_death(alert.run_id)
        await asyncio.to_thread(notify.push, f"groom: {alert.rule}", alert.message)
        ended = projection.ended_of(state.RUNS.get(alert.run_id)) if alert.rule == "ENDED" else None
        await _broadcast_notify(f"[{alert.rule}] {alert.message}", alert.rule, bool(ended and ended["failed"]))


_FEED_QUEUE_MAX = 200


def _feed_put(queue: asyncio.Queue, event: AttentionEvent, ts: float) -> None:
    """Queue one event for a feed without ever blocking the collector: a full queue drops it."""
    try:
        queue.put_nowait((ts, event))
    except asyncio.QueueFull:
        pass
