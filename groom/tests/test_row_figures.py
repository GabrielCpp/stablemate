"""The figures on a run row: cost with coverage, active time and items, kept in the hot cache."""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading
from pathlib import Path

import pytest

from groom import app as groom_app
from groom import cli, figures, projection, state, store
from groom.models import RunTelemetry, WorkflowContainer, WorkflowState


class _DB:
    def __enter__(self) -> _DB:
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(self._tmp.name) / "groom.db")
        store.reset()
        return self

    def __exit__(self, *exc: object) -> None:
        store.reset()
        if self._previous is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = self._previous
        self._tmp.cleanup()


def _span(span_id: str, parent: str, node: str, name: str, attrs: dict, at: float, seconds: float = 60) -> dict:
    return {
        "span_id": span_id, "trace_id": "t", "parent_id": parent, "run_id": "run-1",
        "workflow": "coder", "repo": "acme", "branch": "main", "node": node, "name": name,
        "run_dir": "", "start_ts": at, "end_ts": at + seconds, "status": "OK", "attrs": attrs,
    }


def _seed(progress: tuple[tuple[str, float], ...] = ()) -> None:
    turn = {"backend": "claude", "duration_ms": 60000, "usage.output_tokens": 100}
    spans = [
        _span("s0", "", "work", "work", {"workhorse.span_kind": "state", "workhorse.depth": 0}, 100),
        _span("n1", "s0", "qa", "qa", {"workhorse.depth": 1}, 110),
        _span("t1", "n1", "qa", "agent_turn", {**turn, "total_cost_usd": 1.5}, 120),
        _span("t2", "n1", "qa", "agent_turn", dict(turn), 190),
    ]
    for index, (value, at) in enumerate(progress):
        spans.append(_span(f"p{index}", "s0", "pick", "pick", {"progress": value}, at, 1))
    store.insert_spans(spans)


def test_parse_progress_takes_counts_and_refuses_prose_and_empty_totals() -> None:
    assert store.parse_progress("8/30") == (8, 30)
    assert store.parse_progress(" 0/5 ") == (0, 5)
    assert store.parse_progress("0/0") is None
    assert store.parse_progress("reviewing the story 1/3") is None
    assert store.parse_progress(8) is None


def test_items_come_from_the_latest_ended_span_with_a_count() -> None:
    with _DB():
        _seed((("1/30", 200), ("8/30", 400), ("reviewing the plan", 500), ("0/0", 600)))
        assert store.latest_progress("run-1") == (8, 30)
        assert store.latest_progress("other") is None


def test_a_run_that_reports_no_count_has_no_items() -> None:
    with _DB():
        _seed()
        found = figures.run_figures("run-1")
    assert found["items_done"] is None and found["items_total"] is None


def test_the_figures_match_the_terminal_reports() -> None:
    with _DB():
        _seed((("2/4", 200),))
        found = figures.run_figures("run-1")
        costs = store.node_costs("run-1", limit=1000)
        profile = store.run_profile("run-1")
    assert profile is not None
    assert found["cost_usd"] == sum(row["cost_usd"] or 0 for row in costs) == 1.5
    assert (found["priced_turns"], found["turns"]) == (1, 2)
    assert found["active_s"] == store.active_seconds(profile["time_s"])
    assert found["active_s"] > 0
    assert (found["items_done"], found["items_total"]) == (2, 4)
    assert found["finished"] is True and found["reports_cost"] is True


def test_active_time_leaves_out_waits_gaps_and_unclassified() -> None:
    time_s = {"agent": 10.0, "deterministic": 5.0, "infra": 1.0, "wait": 99.0, "resume_gap": 50.0, "unclassified": 7.0}
    assert store.active_seconds(time_s) == 16.0


def test_the_profile_prints_the_active_figure() -> None:
    with _DB():
        _seed()
        result = store.run_profile("run-1")
    assert "active=" in cli._format_profile(result)


def test_a_run_with_nothing_finished_has_no_cost_and_no_flows() -> None:
    with _DB():
        found = figures.run_figures("run-1")
    assert found["finished"] is False
    assert found["cost_usd"] is None


def test_the_row_carries_the_cached_figures_and_the_order_is_unchanged() -> None:
    cached = {"finished": True, "reports_cost": True, "cost_usd": 3.0, "turns": 4, "priced_turns": 3,
              "active_s": 90.0, "items_done": 1, "items_total": 2}
    runs = {
        "a": RunTelemetry(run_id="a", last_heartbeat_ts=100.0, figures=cached),
        "b": RunTelemetry(run_id="b", last_heartbeat_ts=100.0),
    }
    workflows = [
        WorkflowContainer(container_id="b", name="b", run_id="b", state=WorkflowState.RUNNING),
        WorkflowContainer(container_id="a", name="a", run_id="a", state=WorkflowState.RUNNING),
    ]
    saved = dict(state.RUNS)
    state.RUNS.clear()
    state.RUNS.update(runs)
    try:
        rows = projection.fleet_rows(workflows, now=101.0)
    finally:
        state.RUNS.clear()
        state.RUNS.update(saved)
    assert [row["id"] for row in rows] == ["a", "b"]
    assert rows[0]["figures"] == cached
    assert rows[1]["figures"] is None


def test_refreshes_coalesce_to_one_running_and_one_rerun(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    calls: list[str] = []

    def slow(run_id: str) -> dict:
        calls.append(run_id)
        gate.wait(5)
        return {"n": len(calls)}

    async def quiet() -> None:
        return None

    monkeypatch.setattr(figures, "run_figures", slow)
    monkeypatch.setattr(groom_app, "_broadcast_shell", lambda changed="": quiet())
    state.RUNS["r1"] = RunTelemetry(run_id="r1")

    async def scenario() -> None:
        first = asyncio.create_task(groom_app._refresh_figures("r1"))
        await asyncio.sleep(0.05)
        for _ in range(5):
            await groom_app._refresh_figures("r1")
        gate.set()
        await first

    try:
        asyncio.run(scenario())
        assert calls == ["r1", "r1"]
        assert state.RUNS["r1"].figures == {"n": 2}
    finally:
        state.RUNS.pop("r1", None)


def test_a_batch_refreshes_only_runs_without_figures_when_not_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def record(run_id: str) -> None:
        seen.append(run_id)

    monkeypatch.setattr(groom_app, "_refresh_figures", record)
    state.RUNS["fresh"] = RunTelemetry(run_id="fresh", figures={"x": 1})
    state.RUNS["new"] = RunTelemetry(run_id="new")

    async def scenario() -> None:
        groom_app._schedule_figures([{"run_id": "fresh"}, {"run_id": "new"}], stale=False)
        await asyncio.sleep(0.05)
        groom_app._schedule_figures([{"run_id": "fresh"}], stale=True)
        await asyncio.sleep(0.05)

    try:
        asyncio.run(scenario())
    finally:
        state.RUNS.pop("fresh", None)
        state.RUNS.pop("new", None)
    assert seen == ["new", "fresh"]
