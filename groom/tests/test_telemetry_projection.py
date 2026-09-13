"""Telemetry remains authoritative across stale row snapshots and gate transitions."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from groom import alerts, app, projection, state, store
from groom.models import GateInfo, RunTelemetry, WorkflowContainer, WorkflowState
from workhorse import gates as gate_file


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "RUNS", {})
    monkeypatch.setattr(state, "WORKFLOWS", {})
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    store.reset()
    yield
    store.reset()


def test_shutdown_metric_flush_cannot_reopen_a_completed_generation():
    session = {"run_id": "r", "pid": 11, "resume_generation": 1}
    alerts.ingest_spans([{
        **session, "name": "run:okf-builder", "end_ts": 100,
        "attrs": {"workhorse.terminal": "terminal"},
    }], now=100)
    # Workhorse shuts down the meter provider after closing the root span. Its
    # cumulative metrics therefore receive a collection timestamp after the end.
    alerts.ingest_metrics([{
        **session, "name": "workhorse.node.active", "value": 0,
        "ts": 101, "attrs": {"node": "commit"},
    }], now=101)
    tel = state.RUNS["r"]
    wf = WorkflowContainer(container_id="r", name="test")
    assert projection.liveness(wf, tel, now=1000) == ("done", "terminal")

    alerts.ingest_metrics([{
        **session, "pid": 12, "resume_generation": 2,
        "name": "workhorse.run.heartbeat", "value": 1, "ts": 1001,
    }], now=1001)
    assert projection.liveness(wf, tel, now=1001) == ("live", "alive")
    # A delayed flush from generation 1 must not undo generation 2's activity.
    alerts.ingest_spans([{
        **session, "name": "run:okf-builder", "end_ts": 100,
        "attrs": {"workhorse.terminal": "terminal"},
    }], now=1002)
    assert projection.liveness(wf, tel, now=1002) == ("live", "alive")


def test_detail_uses_current_telemetry_instead_of_stale_workflow():
    wf = WorkflowContainer(container_id="r", name="test", state=WorkflowState.BLOCKED,
                           current_node="old", activity="old", pid=4)
    wf.gates["old"] = GateInfo(workflow_id="r", file_path="old")
    tel = RunTelemetry(run_id="r", current_node="new", activity="new", pid=5)
    detail = projection.run_detail(wf, tel)
    assert detail["state"] == "running"
    assert detail["node"] == "new"
    assert detail["gates"] == []
    assert detail["head"]["activity"] == "new"
    assert detail["head"]["pid"] == 5


def test_parked_run_shows_only_the_complete_latest_questions():
    previous = gate_file.format_operator_gate("Old question?")
    answered = gate_file.apply_answer(previous, "Old answer.")
    latest = "Choose a backend?\n\n### Evidence\n\n" + "Evidence. " * 500 + "\n\nProceed?"
    rearmed = gate_file.append_operator_gate(answered, latest)
    wf = WorkflowContainer(container_id="r", name="test")
    tel = RunTelemetry(run_id="r", wait_kind="operator", wait_gate_path="gate.md",
                       wait_gate_question=rearmed)

    detail = projection.run_detail(wf, tel)

    assert detail["gates"][0]["question"] == latest
    assert detail["gates"][0]["preview"] == "Choose a backend?"


def test_zero_live_metrics_do_not_resurrect_stored_wait():
    wf = WorkflowContainer(container_id="r", name="test")
    tel = RunTelemetry(run_id="r", current_node="new", turn_active=False)
    facts = {"wait_kind": "operator", "wait_elapsed_s": 50,
             "node_elapsed_s": 60, "turn_idle_s": 120}
    cells = {c["key"]: c["value"] for c in projection.metrics(wf, tel, facts)["cells"]}
    assert cells["wait"] == "—"
    assert cells["in node"] == "—"


def test_every_metric_updates_telemetry_freshness_and_clears_non_gate_wait():
    tel = RunTelemetry(run_id="r", wait_kind="operator", wait_gate_path="gate",
                       wait_gate_question="old")
    state.RUNS["r"] = tel
    alerts.ingest_metrics([{"run_id": "r", "name": "workhorse.wait.active",
                           "value": 1, "attrs": {"wait_kind": "cap"}}], now=123)
    assert tel.last_telemetry_ts == 123
    assert tel.wait_gate_path == ""
    assert tel.wait_gate_question == ""


def test_native_gate_context_reads_only_the_reported_absolute_path(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    gate = tmp_path / "gate.md"
    gate.write_text("STATUS: AWAITING\n\nQuestion", encoding="utf-8")
    tel = RunTelemetry(run_id="r", native=True, workspace=str(workspace),
                       wait_kind="operator", wait_gate_path=str(gate))
    app._sync_native_row(tel)
    async def read(path):
        return await app.file_content.fn("r", path=path)

    result = asyncio.run(read(str(gate)))
    assert result["content"] == gate.read_text(encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("unrelated", encoding="utf-8")
    result = asyncio.run(read(str(other)))
    assert result["content"] == ""


def test_native_gate_question_change_triggers_update_and_attendance(tmp_path):
    tel = RunTelemetry(run_id="r", native=True, workspace=str(tmp_path),
                       wait_kind="operator", wait_gate_path=str(tmp_path / "gate.md"),
                       wait_gate_question="first")
    with patch.object(app.attend, "attend_gate") as attend_gate:
        assert app._sync_native_row(tel)
        tel.wait_gate_question = "second"
        assert app._sync_native_row(tel)
        assert attend_gate.call_args.kwargs["question"] == "second"


def test_native_absolute_gate_answer_falls_back_to_its_own_directory(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    gate = tmp_path / "gate.md"
    gate.write_text("STATUS: AWAITING_OPERATOR\n\nQuestion", encoding="utf-8")
    tel = RunTelemetry(run_id="r", native=True, workspace=str(workspace),
                       wait_kind="operator", wait_gate_path=str(gate))
    state.RUNS["r"] = tel
    app._sync_native_row(tel)
    result = asyncio.run(app._answer(state.WORKFLOWS["r"], "r", str(gate), "Proceed"))
    assert result.ok
    assert "Proceed" in gate.read_text(encoding="utf-8")
    # An acknowledged command does not invent a telemetry transition.
    detail = projection.run_detail(state.WORKFLOWS["r"], tel)
    assert detail["state"] == "blocked"
    assert detail["gates"][0]["file_path"] == str(gate)


def test_new_session_heartbeat_replaces_old_live_state_and_rejects_old_session():
    tel = RunTelemetry(run_id="r", last_session=(11, "1"), current_node="old",
                       wait_kind="operator", wait_gate_path="gate", activity="old",
                       turn_active=True, turn_idle_s=300, node_elapsed_s=99,
                       first_seen_ts=5, node_counts={"completed": 3})
    state.RUNS["r"] = tel
    alerts.ingest_metrics([{"run_id": "r", "pid": 12, "resume_generation": 2,
                           "name": "workhorse.run.heartbeat", "value": 1, "ts": 100}], now=100)
    assert tel.last_session == (12, "2")
    assert (tel.wait_kind, tel.wait_gate_path, tel.current_node, tel.activity) == ("", "", "", "")
    assert tel.turn_active is None and tel.node_elapsed_s == 0
    assert tel.first_seen_ts == 5 and tel.node_counts == {"completed": 3}
    alerts.ingest_metrics([{"run_id": "r", "pid": 11, "resume_generation": 1,
                           "name": "workhorse.wait.active", "value": 1,
                           "attrs": {"wait_kind": "operator", "gate_path": "old"}}], now=101)
    alerts.ingest_spans([{"run_id": "r", "pid": 11, "resume_generation": 1,
                         "name": "run:demo", "end_ts": 99}], now=102)
    assert tel.pid == 12 and tel.wait_kind == "" and tel.terminal == ""
    assert tel.last_telemetry_ts == 100


@pytest.mark.parametrize("old_first", [False, True])
@pytest.mark.parametrize("same_path", [False, True])
def test_retained_closed_wait_series_cannot_clear_a_reopened_gate(old_first, same_path):
    active = {"node": "work", "wait_kind": "operator", "gate_path": "A"}
    closed = {"node": "work", "wait_kind": "operator", "gate_path": "B"}
    if same_path:
        closed["gate_path"] = "A"
        closed["gate_question"] = "old question"
        active["gate_question"] = "new question"
    points = [
        {"run_id": "r", "name": "workhorse.wait.active", "value": 1, "attrs": active},
        {"run_id": "r", "name": "workhorse.wait.active", "value": 0, "attrs": closed},
        {"run_id": "r", "name": "workhorse.wait.elapsed_s", "value": 42, "attrs": active},
        {"run_id": "r", "name": "workhorse.wait.elapsed_s", "value": 0, "attrs": closed},
    ]
    if old_first:
        points = [points[1], points[0], points[3], points[2]]
    alerts.ingest_metrics(points)
    tel = state.RUNS["r"]
    assert tel.wait_gate_path == "A" and tel.wait_kind == "operator"
    assert tel.wait_elapsed_s == 42
