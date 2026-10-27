"""The /feed socket, its digest builder and the `groom feed` command."""
from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from litestar import Litestar
from litestar.testing import TestClient

from groom import cli, digest, state, store
from groom import app as groom_app
from groom.alerts import Alert
from groom.attention import AttentionEvent
from groom.models import RunTelemetry

NOW = 10_000.0


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    monkeypatch.setattr(state, "RUNS", {})
    monkeypatch.setattr(state, "WORKFLOWS", {})
    monkeypatch.setattr(state, "CLIENTS", set())
    monkeypatch.setattr(state, "WATCHING", {})
    monkeypatch.setattr(state, "FEEDS", {})
    monkeypatch.setattr(state, "EVENTS", {})
    store.reset()
    yield
    store.reset()


_ids = iter(range(1, 100_000))


def _span(
    name: str, start: float, node: str = "", *, run: str = "acme", attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "span_id": f"s{next(_ids)}", "trace_id": "t1", "parent_id": "", "run_id": run,
        "workflow": "coder", "node": node, "name": name, "start_ts": start,
        "end_ts": start + 1, "attrs": attrs or {}, "resume_generation": 1,
    }


def _turn(start: float, node: str, cost: float, tokens: int, work_id: str = "") -> dict[str, Any]:
    attrs: dict[str, Any] = {"total_cost_usd": cost, "usage.output_tokens": tokens}
    if work_id:
        attrs["work_id"] = work_id
    return _span("agent_turn", start, node, attrs=attrs)


def _log(ts: float, severity: str, body: str, run: str = "acme") -> dict[str, Any]:
    return {"run_id": run, "node": "audit", "severity": severity, "body": body, "ts": ts}


def _clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def test_digest_groups_nodes_and_sums_cost() -> None:
    store.insert_spans([
        _span("audit", 9_100, "audit"),
        _turn(9_101, "audit", 1.5, 100, "a"),
        _turn(9_102, "audit", 0.5, 50, "a"),
        _turn(9_103, "audit", 0.25, 25, "b"),
        _span("plan", 9_200, "plan"),
        _turn(9_201, "plan", 2.0, 10),
        _span("audit", 9_200, "audit", run="globex"),
        _span("old", 5_000, "plan"),
    ])
    frame = digest.build_digest("acme", 9_000, NOW, now=NOW)
    by_node = {visit.node: visit for visit in frame.window.nodes}
    assert set(by_node) == {"audit", "plan"}
    assert by_node["audit"].visits == 1
    assert by_node["audit"].turns == 3
    assert by_node["audit"].cost_usd == pytest.approx(2.25)
    assert by_node["audit"].output_tokens == 175
    assert frame.window.turns == 4
    assert frame.window.cost_usd == pytest.approx(4.25)
    assert frame.window.output_tokens == 185
    assert not frame.quiet


def test_digest_charges_a_resumed_turn_from_a_report_before_its_window() -> None:
    session = {"backend": "claude", "session.id": "s-1"}
    store.insert_spans([
        _span("agent_turn", 8_000, "dev-plan", attrs={**session, "total_cost_usd": 4.0}),
        _span("agent_turn", 9_100, "dev-build", attrs={**session, "total_cost_usd": 6.5}),
    ])
    frame = digest.build_digest("acme", 9_000, NOW, now=NOW)
    assert frame.window.cost_usd == pytest.approx(2.5)


def test_digest_laps_count_turns_per_work_item() -> None:
    store.insert_spans([
        _turn(9_101, "audit", 1.0, 1, "a"),
        _turn(9_102, "audit", 1.0, 1, "a"),
        _turn(9_103, "audit", 1.0, 1, "a"),
        _turn(9_104, "audit", 1.0, 1, "a"),
        _turn(9_105, "audit", 1.0, 1, "b"),
        _turn(9_106, "audit", 1.0, 1, "b"),
    ])
    frame = digest.build_digest("acme", 9_000, NOW, now=NOW)
    laps = {(lap.node, lap.work_id): lap.turns for lap in frame.window.laps}
    assert laps == {("audit", "a"): 4, ("audit", "b"): 2}
    assert "lap 4 on audit (2 items)" in frame.summary


def test_digest_lists_operator_gates_and_warnings() -> None:
    store.insert_spans([
        _span("wait:operator", 9_300, "review", attrs={
            "workhorse.span_kind": "wait", "workhorse.wait_kind": "operator",
            "workhorse.gate_question": "Proceed?", "workhorse.wait_outcome": "answered",
        }),
        _span("wait:machine", 9_310, "review", attrs={
            "workhorse.span_kind": "wait", "workhorse.wait_kind": "machine",
        }),
    ])
    store.insert_logs([
        _log(9_400, "INFO", "fine"),
        _log(9_401, "WARNING", "slow"),
        _log(5_000, "ERROR", "too old"),
    ])
    frame = digest.build_digest("acme", 9_000, NOW, now=NOW)
    assert [(gate.kind, gate.node, gate.outcome, gate.question) for gate in frame.window.gates] == [
        ("operator", "review", "answered", "Proceed?")
    ]
    assert [(line.level, line.message) for line in frame.window.warnings] == [("WARNING", "slow")]
    assert "1 gate raised" in frame.summary
    assert "1 warning" in frame.summary


def test_digest_is_quiet_on_an_empty_window() -> None:
    store.insert_spans([_span("old", 5_000, "plan")])
    store.insert_logs([_log(9_401, "INFO", "fine")])
    frame = digest.build_digest("acme", 9_000, NOW, now=NOW)
    assert frame.quiet
    assert frame.window.nodes == []


def test_a_warning_or_an_event_breaks_the_quiet() -> None:
    store.insert_logs([_log(9_401, "WARNING", "slow")])
    assert not digest.build_digest("acme", 9_000, NOW, now=NOW).quiet
    event = AttentionEvent(run_id="globex", event="stuck")
    state.record_event("globex", event, 9_500)
    frame = digest.build_digest("globex", 9_000, NOW, now=NOW)
    assert not frame.quiet
    assert frame.window.events == [event]
    assert digest.build_digest("globex", 9_500, NOW, now=NOW).quiet


def test_quiet_summary_reads_the_standing() -> None:
    state.RUNS["acme"] = RunTelemetry(
        run_id="acme", last_beat_ts=NOW, last_heartbeat_ts=NOW, current_node="reground-file",
        node_elapsed_s=47 * 60.0, turn_active=True, turn_idle_s=3.0,
    )
    frame = digest.build_digest("acme", NOW - 1800, NOW, now=NOW)
    assert frame.quiet
    assert frame.standing.node == "reground-file"
    assert frame.summary == (
        f"quiet {_clock(NOW - 1800)}-{_clock(NOW)} · in reground-file 47m 00s"
        " · turn streaming, idle 3.0s · +$0.00"
    )


def test_busy_summary_counts_nodes_turns_and_cost() -> None:
    store.insert_spans([
        _turn(9_101, "audit", 1.5, 1, "a"),
        _turn(9_102, "audit", 1.5, 1, "a"),
        _turn(9_103, "plan", 1.1, 1),
    ])
    store.insert_logs([_log(9_401, "WARNING", "slow"), _log(9_402, "ERROR", "bad")])
    frame = digest.build_digest("acme", 9_000, NOW, now=NOW)
    assert frame.summary == (
        f"{_clock(9_000)}-{_clock(NOW)} · 2 nodes, 3 turns, +$4.10"
        " · lap 2 on audit (1 items) · 2 warnings"
    )


def test_query_logs_since_ts_is_a_lower_bound() -> None:
    store.insert_logs([_log(100, "INFO", "a"), _log(200, "INFO", "b"), _log(300, "INFO", "c")])
    rows = store.query_logs(run="acme", since_ts=200)
    assert sorted(row["body"] for row in rows) == ["b", "c"]
    rows = store.query_logs(run="acme", since_ts=200, before_ts=300)
    assert [row["body"] for row in rows] == ["b"]


def _client() -> TestClient:
    return TestClient(Litestar(route_handlers=[groom_app.feed_ws]))


def test_feed_opens_with_standing_events_then_a_digest() -> None:
    state.RUNS["acme"] = RunTelemetry(run_id="acme", terminal="failed", current_node="build")
    state.RUNS["globex"] = RunTelemetry(run_id="globex", terminal="success")
    with _client() as client, client.websocket_connect("/feed?run=acme") as socket:
        first = socket.receive_json()
        second = socket.receive_json()
    assert first["type"] == "event"
    assert first["event"]["run_id"] == "acme"
    assert first["event"]["event"] == "ended"
    assert second["type"] == "digest"
    assert second["standing"]["terminal"] == "failed"
    assert [first["seq"], second["seq"]] == [1, 2]


def test_feed_for_an_unknown_run_waits_with_a_digest() -> None:
    with _client() as client, client.websocket_connect("/feed?run=missing") as socket:
        frame = socket.receive_json()
    assert frame["type"] == "digest"
    assert frame["quiet"] is True
    assert frame["until"] - frame["since"] == pytest.approx(1800, abs=5)


def test_feed_since_replays_events_then_digests_from_the_cursor() -> None:
    state.record_event("acme", AttentionEvent(run_id="acme", event="stuck"), 100.0)
    state.record_event("acme", AttentionEvent(run_id="acme", event="stalled"), 200.0)
    state.record_event("acme", AttentionEvent(run_id="acme", event="churn"), 300.0)
    state.record_event("globex", AttentionEvent(run_id="globex", event="died"), 250.0)
    with _client() as client, client.websocket_connect("/feed?run=acme&since=150") as socket:
        frames = [socket.receive_json() for _ in range(3)]
    assert [frame["type"] for frame in frames] == ["event", "event", "digest"]
    assert [frame["event"]["event"] for frame in frames[:2]] == ["stalled", "churn"]
    assert [frame["seq"] for frame in frames] == [1, 2, 3]
    assert frames[2]["since"] == 150.0


def test_feed_every_below_the_minimum_is_clamped() -> None:
    with _client() as client, client.websocket_connect("/feed?run=acme&every=5") as socket:
        frame = socket.receive_json()
    assert frame["until"] - frame["since"] == pytest.approx(60, abs=5)


def test_feed_requires_a_run() -> None:
    with _client() as client, pytest.raises(Exception):  # noqa: B017, PT011
        with client.websocket_connect("/feed") as socket:
            socket.receive_json()


def dispatch(client: TestClient, alert: Alert) -> None:
    with client.portal() as portal:
        portal.call(groom_app._dispatch_alerts, [alert])


def test_dispatched_event_reaches_only_the_feed_of_its_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(groom_app.notify, "push", lambda title, message: None)
    state.RUNS["acme"] = RunTelemetry(run_id="acme", current_node="review", wait_gate_question="Proceed?")
    with _client() as client:
        with (
            client.websocket_connect("/feed?run=acme") as mine,
            client.websocket_connect("/feed?run=globex") as other,
        ):
            assert mine.receive_json()["type"] == "digest"
            assert other.receive_json()["type"] == "digest"
            dispatch(client, Alert("acme", "BLOCKED", "operator needed"))
            frame = mine.receive_json()
            assert frame["type"] == "event"
            assert frame["event"]["event"] == "blocked"
            assert frame["event"]["question"] == "Proceed?"
            assert frame["seq"] == 2
            dispatch(client, Alert("globex", "STUCK", "idle"))
            assert other.receive_json()["event"]["run_id"] == "globex"
    assert [e.event for _, e in state.EVENTS["acme"]] == ["blocked"]
    assert state.FEEDS == {}


def test_feed_digest_timer_sends_a_quiet_digest_when_nothing_happens() -> None:
    with (
        patch.object(groom_app, "FEED_MIN_EVERY_S", 0.01),
        _client() as client,
        client.websocket_connect("/feed?run=acme&every=0.05") as socket,
    ):
        first = socket.receive_json()
        second = socket.receive_json()
    assert first["type"] == second["type"] == "digest"
    assert second["quiet"] is True
    assert second["seq"] == 2
    assert second["since"] == pytest.approx(first["until"])


def test_evict_runs_drops_recorded_events() -> None:
    state.record_event("acme", AttentionEvent(run_id="acme", event="stuck"), 1.0)
    state.evict_runs(["acme"])
    assert "acme" not in state.EVENTS


@pytest.mark.parametrize("value,seconds", [("30m", 1800.0), ("3600s", 3600.0), ("900", 900.0), ("1h", 3600.0)])
def test_feed_every_parses_durations(
    value: str, seconds: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(cli, "feed", lambda **kwargs: seen.update(kwargs))
    cli.main(["feed", "--run", "acme", "--every", value, "--since", "12.5"])
    assert seen["every_s"] == seconds
    assert seen["since"] == 12.5
    assert seen["run"] == "acme"


def test_feed_every_defaults_to_thirty_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(cli, "feed", lambda **kwargs: seen.update(kwargs))
    cli.main(["feed", "--run", "acme"])
    assert seen["every_s"] == 1800.0
    assert seen["since"] is None


@pytest.mark.parametrize("value", ["soon", "0", "-5m", ""])
def test_feed_bad_every_is_usage_error(value: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["feed", "--run", "acme", "--every", value])
    assert exit_info.value.code == 2
