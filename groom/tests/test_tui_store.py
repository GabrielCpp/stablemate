from __future__ import annotations

from dataclasses import replace

import pytest
import _tui_support as support
from groom import state
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
