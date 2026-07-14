"""Tests for groom's collector role: OTLP decode (groom.otlp), the SQLite
store (groom.store), the alert rules (groom.alerts), AFK push (groom.notify),
and the /v1/traces + /v1/metrics receivers wired through the app.

Payloads are built with the real opentelemetry-proto classes (the same wire
format the workhorse SDK exporter sends), so the decode path is exercised
end-to-end without an OTel SDK. The DB is pointed at a temp file via GROOM_DB.

Run: uv run pytest tests/test_telemetry.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from litestar.testing import TestClient
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from groom import alerts, discovery, notify, otlp, state, store
from groom import app as groom_app
from groom import render

_SPAN_IDS = iter(f"{i:016x}" for i in range(1, 10_000))


def _trace_request(specs: list[dict], resource: dict | None = None) -> bytes:
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    for key, value in (resource or {"run_id": "run-1", "workflow": "coder"}).items():
        kv = resource_spans.resource.attributes.add()
        kv.key, kv.value.string_value = key, value
    scope_spans = resource_spans.scope_spans.add()
    for spec in specs:
        span = scope_spans.spans.add()
        span.trace_id = bytes.fromhex(spec.get("trace_id", "aa" * 16))
        span.span_id = bytes.fromhex(spec.get("span_id") or next(_SPAN_IDS))
        span.name = spec["name"]
        span.start_time_unix_nano = int(spec.get("start", 1000.0) * 1e9)
        span.end_time_unix_nano = int(spec.get("end", 1001.0) * 1e9)
        if spec.get("node"):
            kv = span.attributes.add()
            kv.key, kv.value.string_value = "workhorse.node", spec["node"]
        for name in spec.get("events", []):
            span.events.add().name = name
        if spec.get("error"):
            span.status.code = 2
        if spec.get("terminal"):
            kv = span.attributes.add()
            kv.key, kv.value.string_value = "workhorse.terminal", spec["terminal"]
    return request.SerializeToString()


def _metrics_request(name: str, run_id: str = "run-1", value: int = 1) -> bytes:
    request = ExportMetricsServiceRequest()
    resource_metrics = request.resource_metrics.add()
    kv = resource_metrics.resource.attributes.add()
    kv.key, kv.value.string_value = "run_id", run_id
    metric = resource_metrics.scope_metrics.add().metrics.add()
    metric.name = name
    point = metric.sum.data_points.add()
    point.as_int = value
    point.time_unix_nano = int(2000 * 1e9)
    return request.SerializeToString()


class _TelemetryEnv:
    """Fresh GROOM_DB temp file + cleared hot cache around each test."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["GROOM_DB"] = str(Path(self._tmp.name) / "groom.db")
        store.reset()
        state.RUNS.clear()
        return self

    def __exit__(self, *exc):
        store.reset()
        state.RUNS.clear()
        os.environ.pop("GROOM_DB", None)
        self._tmp.cleanup()


def _hermetic_client() -> TestClient:
    with patch.object(discovery, "scan", return_value=[]), \
         patch.object(discovery, "present_container_ids", return_value=None):
        client = TestClient(app=groom_app.create_app())
        client.__enter__()
    return client


# --------------------------------------------------------------------------- #
# otlp decode + store
# --------------------------------------------------------------------------- #
def test_parse_traces_extracts_identity_node_and_events():
    body = _trace_request(
        [{"name": "plan", "node": "plan", "start": 10.0, "end": 12.5, "events": ["cap_wait"]}]
    )
    spans = otlp.parse_traces(body)
    assert len(spans) == 1
    span = spans[0]
    assert span["run_id"] == "run-1" and span["workflow"] == "coder"
    assert span["node"] == "plan" and span["status"] == "UNSET"
    assert span["end_ts"] - span["start_ts"] == 2.5
    assert span["attrs"]["events"][0]["name"] == "cap_wait"


def test_store_roundtrip_and_query_filters():
    with _TelemetryEnv():
        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [
                        {"name": "plan", "node": "plan", "start": 10, "end": 11},
                        {"name": "build", "node": "build", "start": 20, "end": 80, "error": True},
                    ]
                )
            )
        )
        assert len(store.query_spans()) == 2
        assert store.query_spans(node="plan")[0]["name"] == "plan"
        assert store.query_spans(status="error")[0]["node"] == "build"
        assert [s["node"] for s in store.query_spans(slower_than=30)] == ["build"]
        assert store.query_spans(run="other-run") == []
        # Re-ingesting the same span id (exporter retry) must not duplicate.
        existing_id = store.query_spans(node="plan")[0]["span_id"]
        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [{"name": "plan", "node": "plan", "span_id": existing_id, "start": 10, "end": 11}]
                )
            )
        )
        assert len(store.query_spans(node="plan")) == 1


def test_run_summaries_flag_finished_and_errors():
    with _TelemetryEnv():
        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [
                        {"name": "plan", "node": "plan", "start": 10, "end": 11, "error": True},
                        {"name": "run:coder", "start": 5, "end": 100, "terminal": "fail"},
                    ]
                )
            )
        )
        summary = store.run_summaries()[0]
        assert summary["run_id"] == "run-1"
        assert summary["error_count"] == 1 and summary["finished"] == 1


def test_prune_drops_only_old_rows():
    with _TelemetryEnv():
        store.insert_spans(
            otlp.parse_traces(_trace_request([{"name": "old", "start": 10, "end": 20}]))
        )
        removed = store.prune(retention_days=1, now=20 + 2 * 86400)
        assert removed == 1 and store.query_spans() == []


# --------------------------------------------------------------------------- #
# alert rules
# --------------------------------------------------------------------------- #
def test_watchdog_and_giveup_fire_once_per_run():
    with _TelemetryEnv():
        spans = otlp.parse_traces(
            _trace_request(
                [
                    {"name": "agent_turn", "node": "impl", "events": ["watchdog_kill"]},
                    {"name": "qa_give_up", "node": "qa_give_up"},
                ]
            )
        )
        fired = alerts.ingest_spans(spans, now=100.0)
        assert sorted(a.rule for a in fired) == ["GAVE-UP", "WATCHDOG"]
        # Dedupe per (run_id, rule): the same evidence again fires nothing.
        assert alerts.ingest_spans(spans, now=101.0) == []


def test_churn_fires_on_node_repeats_and_resets_on_refuel():
    with _TelemetryEnv(), patch.dict(os.environ, {"GROOM_CHURN_REPEATS": "3"}):
        one_visit = otlp.parse_traces(
            _trace_request([{"name": "fix", "node": "fix", "start": 1, "end": 2}])
        )
        assert alerts.ingest_spans(one_visit, now=10.0) == []
        assert alerts.ingest_spans(one_visit, now=11.0) == []
        # A gas refuel (forward progress) resets the counters...
        alerts.ingest_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.gas.refuels")), now=12.0
        )
        assert alerts.ingest_spans(one_visit, now=13.0) == []
        assert alerts.ingest_spans(one_visit, now=14.0) == []
        # ...so only a third post-refuel repeat trips the rule.
        fired = alerts.ingest_spans(one_visit, now=15.0)
        assert [a.rule for a in fired] == ["CHURN"]


def test_agent_turn_retries_do_not_count_as_churn():
    with _TelemetryEnv(), patch.dict(os.environ, {"GROOM_CHURN_REPEATS": "2"}):
        turns = otlp.parse_traces(
            _trace_request(
                [{"name": "agent_turn", "node": "impl"}, {"name": "agent_turn", "node": "impl"}]
            )
        )
        assert alerts.ingest_spans(turns, now=10.0) == []


def test_stall_fires_on_silence_but_heartbeat_suppresses_it():
    with _TelemetryEnv(), patch.dict(os.environ, {"GROOM_STALL_MIN": "90"}):
        spans = otlp.parse_traces(_trace_request([{"name": "plan", "node": "plan"}]))
        alerts.ingest_spans(spans, now=1000.0)
        # 89 minutes of silence: nothing.
        assert alerts.check_time_rules(now=1000.0 + 89 * 60) == []
        # A cap-wait heartbeat arrives: the run is provably alive...
        alerts.ingest_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.cap_wait.heartbeat")),
            now=1000.0 + 89 * 60,
        )
        # ...so even 91 minutes after the last SPAN there is no STALL.
        assert alerts.check_time_rules(now=1000.0 + 91 * 60) == []
        # But 91 minutes after the last heartbeat, silence means hang.
        fired = alerts.check_time_rules(now=1000.0 + 89 * 60 + 91 * 60)
        assert [a.rule for a in fired] == ["STALL"]


def test_budget_fires_past_max_hours_and_terminal_retires_the_run():
    with _TelemetryEnv(), patch.dict(
        os.environ, {"GROOM_MAX_HOURS": "24", "GROOM_STALL_MIN": "100000"}
    ):
        spans = otlp.parse_traces(_trace_request([{"name": "plan", "node": "plan"}]))
        alerts.ingest_spans(spans, now=0.0)
        assert alerts.check_time_rules(now=23 * 3600) == []
        fired = alerts.check_time_rules(now=25 * 3600)
        assert [a.rule for a in fired] == ["BUDGET"]
        # The root span arriving = the run ended → no further absence alerts
        # (fresh run so the dedupe set is empty).
        state.RUNS.clear()
        alerts.ingest_spans(spans, now=0.0)
        root = otlp.parse_traces(
            _trace_request([{"name": "run:coder", "terminal": "terminal"}])
        )
        alerts.ingest_spans(root, now=1.0)
        assert alerts.check_time_rules(now=48 * 3600) == []


# --------------------------------------------------------------------------- #
# notify
# --------------------------------------------------------------------------- #
def test_notify_posts_to_ntfy_and_webhook_when_configured():
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append((request.full_url, request.data))

        class _Resp:
            def close(self):
                pass

        return _Resp()

    with patch.dict(
        os.environ,
        {"GROOM_NTFY_TOPIC": "my-topic", "GROOM_WEBHOOK_URL": "http://hook.local/x"},
    ), patch.object(notify.urllib.request, "urlopen", fake_urlopen):
        notify.push("groom: STALL", "run-1 silent for 95 min")
    assert calls[0][0] == "https://ntfy.sh/my-topic"
    assert b"silent for 95 min" in calls[0][1]
    assert calls[1][0] == "http://hook.local/x"
    assert b"groom: STALL" in calls[1][1]


def test_notify_noop_without_config_and_swallows_errors():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GROOM_NTFY_TOPIC", None)
        os.environ.pop("GROOM_WEBHOOK_URL", None)
        with patch.object(notify.urllib.request, "urlopen") as urlopen:
            notify.push("t", "m")
        urlopen.assert_not_called()
    with patch.dict(os.environ, {"GROOM_NTFY_TOPIC": "t"}), patch.object(
        notify.urllib.request, "urlopen", side_effect=OSError("down")
    ):
        notify.push("t", "m")  # must not raise


# --------------------------------------------------------------------------- #
# receivers (through the app)
# --------------------------------------------------------------------------- #
def test_v1_traces_receiver_stores_spans_and_fires_alerts():
    with _TelemetryEnv(), patch.object(notify, "push") as push:
        client = _hermetic_client()
        try:
            body = _trace_request(
                [{"name": "agent_turn", "node": "impl", "events": ["watchdog_kill"]}]
            )
            resp = client.post(
                "/v1/traces", content=body, headers={"Content-Type": "application/x-protobuf"}
            )
        finally:
            client.__exit__(None, None, None)
        assert resp.status_code in (200, 201)
        assert store.query_spans(run="run-1")[0]["name"] == "agent_turn"
        assert push.call_args[0][0] == "groom: WATCHDOG"
        assert "run-1" in state.RUNS


def test_v1_metrics_receiver_records_heartbeat():
    with _TelemetryEnv():
        client = _hermetic_client()
        try:
            resp = client.post(
                "/v1/metrics",
                content=_metrics_request("workhorse.cap_wait.heartbeat"),
                headers={"Content-Type": "application/x-protobuf"},
            )
        finally:
            client.__exit__(None, None, None)
        assert resp.status_code in (200, 201)
        assert state.RUNS["run-1"].last_heartbeat_ts > 0


def test_v1_traces_rejects_garbage_with_400():
    with _TelemetryEnv():
        client = _hermetic_client()
        try:
            resp = client.post("/v1/traces", content=b"\xff\xfenot protobuf")
        finally:
            client.__exit__(None, None, None)
        assert resp.status_code == 400


def test_traces_search_endpoint_renders_fragment():
    import time as _time

    now = _time.time()
    with _TelemetryEnv():
        # Recent timestamps: app startup prunes spans older than the retention
        # window, and these must survive it.
        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [
                        {"name": "plan", "node": "plan", "start": now - 20, "end": now - 19},
                        {"name": "build", "node": "build", "start": now - 10, "end": now - 9, "error": True},
                    ]
                )
            )
        )
        client = _hermetic_client()
        try:
            resp = client.get("/traces", params={"status": "ERROR"})
        finally:
            client.__exit__(None, None, None)
        body = resp.text
        assert 'class="traces"' in body and "<td>build</td>" in body
        assert "<td>plan</td>" not in body  # the status filter applied


def test_render_traces_escapes_untrusted_values():
    fragment = render.render_traces(
        [],
        [
            {
                "run_id": "<img src=x>",
                "node": "<script>alert(1)</script>",
                "name": "n",
                "start_ts": 10.0,
                "end_ts": 11.0,
                "status": "OK",
            }
        ],
        {},
    )
    assert "<script>alert" not in fragment and "&lt;script&gt;" in fragment
