from __future__ import annotations

import asyncio
import logging

from groom import (
    alerting,
    alerts,
    live,
    native,
    tasks,
)
from groom.gates import native_questions
from groom.models import (
    RunTelemetry,
)

logger = logging.getLogger(__name__)


async def _backfill_wait_gate(run: RunTelemetry) -> bool:
    """Fetch the live question over the control socket when telemetry's copy of gate_path/gate_question is missing, and say whether it arrived."""
    if not run.native or not run.run_dir:
        return False
    reply = await native_questions(run.run_dir, "gate backfill", run.run_id)
    if not reply or not reply.get("ok"):
        return False
    raw_questions = reply.get("questions")
    questions = [q for q in raw_questions if isinstance(q, dict)] if isinstance(raw_questions, list) else []
    if not questions:
        return False
    question = questions[0]
    run.wait_gate_path = str(question.get("path", ""))
    run.wait_gate_question = str(question.get("question", ""))
    return bool(run.wait_gate_path)


GATE_BACKFILL_RETRY_S = (5.0, 10.0, 20.0)


GATE_BACKFILL_STEADY_S = 60.0


_BACKFILLS: dict[str, asyncio.Task] = {}


def _awaits_gate_path(run: RunTelemetry) -> bool:
    return (
        not run.terminal
        and run.wait_kind in ("operator", "machine")
        and not run.wait_gate_path
    )


async def _backfill_until_found(run: RunTelemetry) -> None:
    """Ask for a waiting run's gate path now, then again after 5, 10 and 20 seconds and every 60 after that, for as long as the wait is open without one."""
    attempt = 0
    try:
        while _awaits_gate_path(run):
            try:
                found = await _backfill_wait_gate(run)
            except Exception:  # noqa: BLE001 - a failed ask is retried, not fatal
                logger.exception("gate backfill failed for %s", run.run_id)
                found = False
            if found:
                fired: list[alerts.Alert] = []
                native._sync_native_row(run, fired)
                await alerting._dispatch_alerts(fired)
                live.mark_fleet()
                return
            delay = GATE_BACKFILL_RETRY_S[attempt] if attempt < len(GATE_BACKFILL_RETRY_S) else GATE_BACKFILL_STEADY_S
            attempt += 1
            await asyncio.sleep(delay)
    finally:
        _BACKFILLS.pop(run.run_id, None)


def _ensure_gate_backfill(run: RunTelemetry) -> None:
    if not run.native or run.run_id in _BACKFILLS or not _awaits_gate_path(run):
        return
    task = tasks.spawn(_backfill_until_found(run), name="gate-backfill")
    _BACKFILLS[run.run_id] = task
