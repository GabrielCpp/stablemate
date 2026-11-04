from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from groom import alerts, app, history, projection, state
from groom.models import RunTelemetry, WorkflowContainer, WorkflowState
from test_projection import _runs_are


def _ended(terminal: str, kind: str = "", fired: set[str] | None = None) -> RunTelemetry:
    return RunTelemetry(run_id="r1", terminal=terminal, terminal_ts=1000.0, error_kind=kind, error_class="Boom", current_node="qa-story", fired=fired or set())


@pytest.mark.parametrize(
    ("terminal", "kind", "fired", "ending", "failed"),
    [
        ("terminal", "", set(), "success", False),
        ("terminal", "", {"GAVE-UP"}, "gave-up", True),
        ("fail", "fatal", set(), "failed", True),
        ("aborted", "", set(), "crashed", True),
        ("interrupted", "fatal", set(), "interrupted", True),
        ("interrupted", "interrupt", set(), "interrupted", False),
    ],
)
def test_a_runs_ending_reads_through_the_history_mapping_and_only_a_failure_is_flagged_failed(terminal, kind, fired, ending, failed):
    ended = projection.ended_of(_ended(terminal, kind, fired))
    assert ended == {
        "ending": ending, "ending_label": history.LABELS[ending], "ended_ts": 1000.0,
        "node": "qa-story", "error_class": "Boom", "failed": failed,
    }


def test_a_run_that_is_running_or_continues_through_a_reload_has_no_ending():
    assert projection.ended_of(None) is None
    assert projection.ended_of(RunTelemetry(run_id="r1")) is None
    assert projection.ended_of(_ended("reload")) is None


def test_the_row_and_the_detail_carry_the_same_ending():
    wf = WorkflowContainer(container_id="r1", name="coder", state=WorkflowState.RUNNING)
    tel = _ended("fail", "fatal")
    row = projection.run_row(wf, tel, now=1010.0)
    detail = projection.run_detail(wf, tel, now=1010.0)
    assert row["ended"] == detail["ended"] and row["ended"]["ending"] == "failed"
    assert row["state"] == "finished"
    assert projection.run_row(wf, RunTelemetry(run_id="r1"), now=1010.0)["ended"] is None


def _root(run: str, terminal: str, end: float, **attrs: str) -> dict:
    return {
        "span_id": f"{run}-{end}", "trace_id": "t", "parent_id": "", "run_id": run, "workflow": "coder", "repo": "acme", "branch": "main",
        "node": "", "name": "run:coder", "run_dir": "", "start_ts": end - 5, "end_ts": end, "status": "OK",
        "attrs": {"workhorse.terminal": terminal, **attrs},
    }


def test_the_root_span_records_why_the_run_ended_and_a_newer_signal_forgets_it():
    now = time.time()
    with _runs_are({}):
        alerts.ingest_spans([_root("r9", "interrupted", now, **{"error.kind": "fatal", "error.class": "RunBudgetExceeded"})], now=now)
        run = state.RUNS["r9"]
        recorded = (run.error_kind, run.error_class)
        later = _root("r9", "", now + 60)
        later["name"] = "agent_turn"
        alerts.ingest_spans([later], now=now + 60)
        cleared = (run.terminal, run.error_kind, run.error_class)
    assert recorded == ("fatal", "RunBudgetExceeded")
    assert cleared == ("", "", "")


def test_a_written_summary_is_announced_to_every_tab():
    queue: asyncio.Queue = asyncio.Queue()
    state.add_client(queue)
    try:
        asyncio.run(_announce_with(queue))
    finally:
        state.remove_client(queue)


async def _announce_with(queue: asyncio.Queue) -> None:
    with patch.object(history, "compute", return_value=None):
        await app._write_summary("r7")
    assert queue.get_nowait() == {"type": "summary", "run_id": "r7"}


def test_the_book_screen_describes_the_ended_strip_and_both_rail_badges() -> None:
    root = Path(__file__).resolve().parents[2] / "docs/services/groom"
    book = (root / "gui/screens/groom-dashboard.md").read_text()
    rules = (root / "concepts/run-ended-notice.md").read_text()
    for heading in ("### ended-strip", "### history-badge", "### open-ended-run-in-history"):
        assert heading in book
    assert "It stays open here." in book
    assert "History, 2 runs failed since you last looked" in book
    assert "the Runs button's badge counts blocked runs while History is open" in book
    assert "- rule: the strip derives from the open run's detail" in rules
    assert "`error.kind` as `fatal`" in rules


def test_a_notify_frame_names_its_rule_and_an_ended_one_says_whether_the_run_failed(monkeypatch: pytest.MonkeyPatch):
    frames: list[dict] = []

    async def _capture(frame: dict) -> None:
        frames.append(frame)

    monkeypatch.setattr(state, "broadcast", _capture)
    asyncio.run(app._broadcast_notify("w: Ship it?"))
    asyncio.run(app._broadcast_notify("[BLOCKED] w", "BLOCKED"))
    asyncio.run(app._broadcast_notify("[ENDED] w", "ENDED", True))
    assert frames == [
        {"type": "notify", "message": "w: Ship it?"},
        {"type": "notify", "message": "[BLOCKED] w", "rule": "BLOCKED"},
        {"type": "notify", "message": "[ENDED] w", "rule": "ENDED", "failed": True},
    ]
