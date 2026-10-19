from __future__ import annotations

from dataclasses import replace

import pytest
import _tui_support as support
from groom import projection, state
from groom.models import GateInfo, WorkflowState
from groom.tui import store as client


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


def _loaded() -> client.Store:
    return client.apply_state(client.Store(), support.state_frame())


def test_state_loads_the_fleet_status_and_scanning():
    state.SCANNING = True
    loaded = client.apply_state(client.Store(), support.state_frame())
    state.SCANNING = False
    assert [row["id"] for row in loaded.runs] == [support.ACME, support.GLOBEX, support.WEBAPP]
    assert loaded.status["workers"] == 3
    assert loaded.scanning is True


def test_a_state_frame_without_status_keeps_the_last_status():
    loaded = _loaded()
    frame = {**support.state_frame(), "status": None}
    assert client.apply_state(loaded, frame).status == loaded.status


def test_a_run_frame_replaces_a_row_and_resorts_by_rank_then_name():
    loaded = _loaded()
    web = state.WORKFLOWS[support.WEBAPP]
    web.state = WorkflowState.BLOCKED
    web.gates["g.md"] = GateInfo(workflow_id=support.WEBAPP, file_path="g.md", question="?")
    merged = client.apply_run(loaded, support.run_frame(support.WEBAPP))
    assert [row["id"] for row in merged.runs] == [support.ACME, support.WEBAPP, support.GLOBEX]
    assert len(merged.runs) == 3


def test_a_run_frame_for_a_new_run_is_inserted_in_order():
    loaded = _loaded()
    state.upsert_workflow(
        "initech12345", name="aaa-first", workflow_type="coder", run_id="run-new",
        state=WorkflowState.BLOCKED,
    )
    merged = client.apply_run(loaded, support.run_frame("initech12345"))
    assert [row["name"] for row in merged.runs][:2] == ["aaa-first", "coder-acme"]
    assert len(merged.runs) == 4


def test_a_run_frame_without_a_row_changes_nothing():
    loaded = _loaded()
    assert client.apply_run(loaded, {"type": "run"}) is loaded


def test_detail_for_the_selected_run_is_stored():
    selected = client.select(_loaded(), support.ACME)
    updated = client.apply_detail(selected, support.detail_frame(support.ACME))
    assert updated.detail is not None
    assert updated.detail["gates"][0]["file_path"] == "context/gate.md"


def test_detail_for_another_run_is_ignored():
    selected = client.select(_loaded(), support.ACME)
    assert client.apply_detail(selected, support.detail_frame(support.GLOBEX)) is selected


def test_selecting_drops_the_previous_detail():
    selected = client.select(_loaded(), support.ACME)
    held = client.apply_detail(selected, support.detail_frame(support.ACME))
    assert client.select(held, support.GLOBEX).detail is None


def test_answered_names_the_gate_only_for_the_selected_run():
    selected = client.select(_loaded(), support.ACME)
    frame = {"type": "answered", "id": support.ACME, "file_path": "context/gate.md"}
    assert client.answered_gate(selected, frame) == "context/gate.md"
    assert client.answered_gate(selected, {**frame, "id": support.GLOBEX}) == ""
    assert client.answered_gate(replace(selected, selected=""), frame) == ""


def _history() -> list[dict]:
    slug = "001-implement"
    return projection.history_lines([
        support.log_row(100.0, "compiled"),
        support.span_row(120.0, "plan"),
        support.metric_row(130.0),
        support.transcript_row(140.0, support.message_update("agent_message_chunk", "done"), slug),
        support.span_row(150.0, "agent_turn", slug),
    ], now=1000.0)


def test_the_all_view_hides_absorbed_spans_and_keeps_turns():
    lines = _history()
    shown = client.trail_lines(lines, "all", "")
    assert [line["kind"] for line in shown] == ["turn", "metric", "span", "log"]
    assert not any(line.get("absorbed") for line in shown)


def test_the_transcript_view_keeps_only_turns():
    shown = client.trail_lines(_history(), "transcript", "")
    assert [line["kind"] for line in shown] == ["turn"]


def test_the_telemetry_view_keeps_everything_but_turns_and_shows_absorbed_spans():
    shown = client.trail_lines(_history(), "telemetry", "")
    assert [line["kind"] for line in shown] == ["span", "metric", "span", "log"]
    assert sum(1 for line in shown if line.get("absorbed")) == 1


@pytest.mark.parametrize(
    ("view", "kind", "expected"),
    [
        ("all", "log", ["log"]),
        ("all", "span", ["span"]),
        ("all", "metric", ["metric"]),
        ("telemetry", "log", ["log"]),
        ("telemetry", "span", ["span", "span"]),
        ("telemetry", "metric", ["metric"]),
    ],
)
def test_a_kind_narrows_the_all_and_telemetry_views(view, kind, expected):
    shown = client.trail_lines(_history(), view, kind)
    assert [line["kind"] for line in shown] == expected


@pytest.mark.parametrize("kind", ["", "log", "span", "metric"])
def test_the_transcript_view_ignores_the_kind_filter(kind):
    shown = client.trail_lines(_history(), "transcript", kind)
    assert [line["kind"] for line in shown] == ["turn"]


def test_an_empty_history_shows_nothing_in_every_view():
    for view in client.TRAIL_VIEWS:
        assert client.trail_lines([], view, "") == []


def test_cycling_the_view_and_the_kind_wraps_around():
    store = client.Store()
    views = []
    for _ in range(4):
        store = client.cycle_view(store)
        views.append(store.trail_view)
    assert views == ["transcript", "telemetry", "all", "transcript"]
    kinds = []
    for _ in range(5):
        store = client.cycle_kind(store)
        kinds.append(store.trail_kind)
    assert kinds == ["log", "span", "metric", "", "log"]


def test_selecting_a_run_keeps_the_chosen_view():
    store = client.cycle_view(client.Store())
    assert client.select(store, support.ACME).trail_view == "transcript"
