"""End-to-end: a native run's OTLP export → the /v1/metrics route → a dashboard row."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from litestar.testing import TestClient
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)

from groom import app as groom_app
from groom import sidecar_hub, state


def _reset() -> None:
    state.WORKFLOWS.clear()
    state.RUNS.clear()
    state._gate_locks.clear()
    sidecar_hub.CONNECTIONS.clear()


def _node_active_export(run_dir: str, workspace: str) -> bytes:
    """A workhorse ``workhorse.node.active`` gauge export carrying the full native resource (run_id/workflow/run_dir/workspace/process.pid) and a ``wf.activity`` point attribute — exactly what otel._Telemetry stamps on the live gauge."""
    req = ExportMetricsServiceRequest()
    rm = req.resource_metrics.add()
    for key, val in (
        ("run_id", "RUN-XYZ"), ("workflow", "coder"), ("repo", "acme"),
        ("branch", "main"), ("run_dir", run_dir), ("workspace", workspace),
    ):
        kv = rm.resource.attributes.add()
        kv.key, kv.value.string_value = key, val
    kv = rm.resource.attributes.add()
    kv.key, kv.value.int_value = "process.pid", 5150
    metric = rm.scope_metrics.add().metrics.add()
    metric.name = "workhorse.node.active"
    point = metric.gauge.data_points.add()
    point.as_double = 1.0
    point.time_unix_nano = int(2000 * 1e9)
    for key, val in (("node", "review"), ("wf.activity", "reviewing PRED-A2JX")):
        a = point.attributes.add()
        a.key, a.value.string_value = key, val
    return req.SerializeToString()


def test_native_metrics_export_materializes_a_dashboard_row():
    _reset()
    with tempfile.TemporaryDirectory() as run_dir, tempfile.TemporaryDirectory() as ws:
        prev = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = os.path.join(run_dir, "groom.db")
        from groom import store
        store.reset()
        try:
            with TestClient(app=groom_app.create_app()) as client:
                resp = client.post(
                    "/v1/metrics",
                    content=_node_active_export(run_dir, ws),
                    headers={"content-type": "application/x-protobuf"},
                )
                assert resp.status_code == 200
                wf = state.WORKFLOWS.get("RUN-XYZ")
                assert wf is not None, "native run did not materialize a dashboard row"
                assert wf.native is True
                assert wf.workflow_type == "coder"
                assert wf.current_node == "review"
                assert wf.activity == "reviewing PRED-A2JX"
                assert wf.pid == 5150
                assert wf.workspace_volume == ws
        finally:
            store.reset()
            if prev is None:
                os.environ.pop("GROOM_DB", None)
            else:
                os.environ["GROOM_DB"] = prev




@pytest.fixture
def native_root():
    with tempfile.TemporaryDirectory(prefix="groom-native-") as directory:
        yield Path(directory)


def test_telemetry_gate_answer_reaches_the_waiting_process(native_root, monkeypatch):
    """An HTTP answer must reach the control socket and persist before the wait ends."""
    from concurrent.futures import ThreadPoolExecutor

    from groom import store
    from workhorse import control, gates
    from workhorse.pyflow.driver import wait_for_answer

    tmp_path = native_root
    _reset()
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    store.reset()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    gate = tmp_path / "decision.md"
    gate.write_text("STATUS: AWAITING_OPERATOR\n\nChoose a backend.\n", encoding="utf-8")
    request = ExportMetricsServiceRequest.FromString(_node_active_export(str(run_dir), str(tmp_path)))
    metric = request.resource_metrics[0].scope_metrics[0].metrics.add()
    metric.name = "workhorse.wait.active"
    point = metric.gauge.data_points.add()
    point.as_double = 1.0
    point.time_unix_nano = time.time_ns()
    for key, value in (("wait_kind", "operator"), ("gate_path", str(gate)),
                       ("gate_question", gate.read_text(encoding="utf-8"))):
        attr = point.attributes.add()
        attr.key, attr.value.string_value = key, value

    async def no_discovery():
        return 0

    async def no_fallback(*args, **kwargs):
        raise AssertionError("a reachable waiting process must persist its own answer")

    monkeypatch.setattr(groom_app.attend, "attend_gate", lambda **kwargs: None)
    monkeypatch.setattr(groom_app, "_reconcile", no_discovery)
    monkeypatch.setattr(groom_app, "answer_gate", no_fallback)
    channel = control.SocketChannel.open(run_dir)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(wait_for_answer, gate, interval=0.05, channel=channel,
                                      deadline=time.time() + 5)
            with TestClient(app=groom_app.create_app()) as client:
                response = client.post("/v1/metrics", content=request.SerializeToString(),
                                       headers={"content-type": "application/x-protobuf"})
                assert response.status_code == 200
                detail = client.get("/worker/RUN-XYZ").json()
                assert detail.get("state") == "blocked", detail
                assert "Choose a backend" in detail["gates"][0]["question"]
                response = client.post("/api/run/RUN-XYZ/outbox", json={
                    "file_path": detail["gates"][0]["file_path"], "answer": "sqlite",
                })
                assert response.json()["ok"] is True
                assert waiting.result(timeout=5) is None
                content = gate.read_text(encoding="utf-8")
                assert gates.status_of(content) == "ANSWERED"
                assert content.endswith("\n\nsqlite\n")
    finally:
        channel.close()
        store.reset()
        _reset()


def test_machine_wait_cannot_be_completed_by_an_operator_answer(tmp_path):
    import asyncio

    from groom import projection
    from groom.models import GateInfo, RunTelemetry, WorkflowContainer

    _reset()
    gate = tmp_path / "machine.md"
    original = "STATUS: AWAITING_OPERATOR\n\nMachine result pending.\n"
    gate.write_text(original, encoding="utf-8")
    wf = WorkflowContainer(container_id="machine", name="machine", native=True,
                           workspace_volume=str(tmp_path), runs_volume=str(tmp_path))
    wf.gates[str(gate)] = GateInfo(workflow_id="machine", file_path=str(gate), kind="machine")
    state.WORKFLOWS["machine"] = wf
    tel = RunTelemetry(run_id="machine", wait_kind="machine", wait_gate_path=str(gate))
    state.RUNS["machine"] = tel
    try:
        detail = projection.run_detail(wf, tel)
        assert detail["gates"][0].get("kind") == "machine"
        result = asyncio.run(groom_app._answer(wf, "machine", str(gate), "pretend done"))
        assert not result.ok
        assert gate.read_text(encoding="utf-8") == original
    finally:
        _reset()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
