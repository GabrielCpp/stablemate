"""End-to-end: a native run's OTLP export → the /v1/metrics route → a dashboard row.

Exercises the real wire path (protobuf decode in groom.otlp, ingest in groom.alerts,
row projection in groom.app) rather than hand-built dicts, so a break anywhere in that
chain — a resource attribute not denormalized, a verdict miscomputed — is caught.

Run: uv run pytest tests/test_native_integration.py
"""
from __future__ import annotations

import os
import tempfile

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
    """A workhorse ``workhorse.node.active`` gauge export carrying the full native
    resource (run_id/workflow/run_dir/workspace/process.pid) and a ``wf.activity``
    point attribute — exactly what otel._Telemetry stamps on the live gauge."""
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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
