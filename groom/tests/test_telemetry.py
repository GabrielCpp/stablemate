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
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from litestar.testing import TestClient
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from groom import alerts, discovery, notify, otlp, projection, state, store
from groom import app as groom_app

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
        # The workflow's rendered `labels:` — what CHURN reads to tell one unit of
        # work from the next. Real spans also carry workhorse.seq/depth, which the
        # signature must ignore; `seq` stamps that in deliberately.
        if spec.get("seq") is not None:
            kv = span.attributes.add()
            kv.key, kv.value.int_value = "workhorse.seq", spec["seq"]
        for key, value in (spec.get("labels") or {}).items():
            kv = span.attributes.add()
            kv.key, kv.value.string_value = key, value
        # Numeric attributes, which is what usage/cost actually arrive as. Their keys
        # only *look* nested (`usage.output_tokens`) — OTel's attribute model is flat,
        # so these land in attrs_json as literal dotted keys.
        for key, value in (spec.get("numbers") or {}).items():
            kv = span.attributes.add()
            kv.key = key
            if isinstance(value, float):
                kv.value.double_value = value
            else:
                kv.value.int_value = value
        for name in spec.get("events", []):
            span.events.add().name = name
        if spec.get("error"):
            span.status.code = 2
        if spec.get("terminal"):
            kv = span.attributes.add()
            kv.key, kv.value.string_value = "workhorse.terminal", spec["terminal"]
    return request.SerializeToString()


def _metrics_request(
    name: str,
    run_id: str = "run-1",
    value: float = 1,
    *,
    node: str | None = None,
    gauge: bool = False,
    ts: float = 2000.0,
    run_dir: str = "",
) -> bytes:
    """One metric point. ``gauge=True`` emits a double gauge (node.active,
    node.elapsed_s, turn.idle_s); the default is an int sum (the heartbeat and
    refuel counters). ``ts`` stamps the point, which is what decides whether it
    is newer than a run's recorded terminal. ``run_dir`` goes on the resource,
    where the receiver's test-run filter reads it."""
    request = ExportMetricsServiceRequest()
    resource_metrics = request.resource_metrics.add()
    kv = resource_metrics.resource.attributes.add()
    kv.key, kv.value.string_value = "run_id", run_id
    if run_dir:
        kv = resource_metrics.resource.attributes.add()
        kv.key, kv.value.string_value = "run_dir", run_dir
    metric = resource_metrics.scope_metrics.add().metrics.add()
    metric.name = name
    if gauge:
        point = metric.gauge.data_points.add()
        point.as_double = float(value)
    else:
        point = metric.sum.data_points.add()
        point.as_int = int(value)
    if node is not None:
        kv = point.attributes.add()
        kv.key, kv.value.string_value = "node", node
    point.time_unix_nano = int(ts * 1e9)
    return request.SerializeToString()


def _logs_request(
    records: list[dict],
    resource: dict | None = None,
) -> bytes:
    """One ExportLogsServiceRequest. ``severity`` is the OTLP severity_number
    (9=INFO, 13=WARN, 17=ERROR); ``severity_text`` mimics what the SDK writes,
    which is deliberately NOT the stdlib name for warnings."""
    request = ExportLogsServiceRequest()
    resource_logs = request.resource_logs.add()
    for key, value in (
        resource or {"run_id": "run-1", "workflow": "okf-builder", "run_dir": "/runs/r1"}
    ).items():
        kv = resource_logs.resource.attributes.add()
        kv.key, kv.value.string_value = key, value
    scope_logs = resource_logs.scope_logs.add()
    for spec in records:
        record = scope_logs.log_records.add()
        record.body.string_value = spec.get("body", "hello")
        record.severity_number = spec.get("severity", 9)
        record.severity_text = spec.get("severity_text", "")
        record.time_unix_nano = int(spec.get("ts", 1000.0) * 1e9)
        for key, value in (spec.get("attrs") or {}).items():
            kv = record.attributes.add()
            kv.key, kv.value.string_value = key, value
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


_TURN = {
    "duration_ms": 230746,
    "total_cost_usd": 1.3442182,
    "usage.input_tokens": 62,
    "usage.output_tokens": 17550,
    "usage.cache_read_input_tokens": 2478104,
    "usage.cache_creation_input_tokens": 55369,
}


def _columns(span_id: str = "") -> dict:
    names = "span_id, duration_ms, total_cost_usd, input_tokens, output_tokens"
    names += ", cache_read_tokens, cache_creation_tokens, pid, resume_generation"
    rows = store._connection().execute(f"SELECT {names} FROM spans ORDER BY span_id")  # noqa: S608
    return {row["span_id"]: dict(row) for row in rows}


def test_usage_and_cost_land_in_promoted_columns_not_only_attrs_json():
    with _TelemetryEnv():
        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [
                        {"name": "agent_turn", "node": "plan-qa", "span_id": "a" * 16,
                         "numbers": _TURN},
                        # A node span: no agent turn under it, so no usage at all.
                        {"name": "assess", "node": "assess", "span_id": "b" * 16},
                    ],
                    resource={
                        "run_id": "run-1",
                        "workflow": "coder",
                        "process.pid": "4242",
                        "workhorse.resume_generation": "2",
                    },
                )
            )
        )
        turn = _columns()["a" * 16]
        assert turn["duration_ms"] == 230746
        assert turn["total_cost_usd"] == 1.3442182
        assert turn["input_tokens"] == 62 and turn["output_tokens"] == 17550
        assert turn["cache_read_tokens"] == 2478104
        assert turn["cache_creation_tokens"] == 55369
        # Parsed from the resource since the collector first shipped, but dropped at
        # insert for want of a column until now.
        assert turn["pid"] == 4242
        # A resume reuses the run_id and opens a fresh root span, so this is what
        # separates a crash-and-resume gap from a process that sat waiting.
        assert turn["resume_generation"] == 2

        # Absent is not zero. A harness that does not report cost reports nothing, and
        # averaging a real 0.0 together with an unknown would understate spend.
        node = _columns()["b" * 16]
        assert node["total_cost_usd"] is None and node["output_tokens"] is None
        assert node["duration_ms"] is None

        # The attributes stay in attrs_json too, so a query written against the old
        # shape keeps working — provided it quotes the dotted key.
        conn = store._connection()
        quoted = "SELECT json_extract(attrs_json, '$.\"usage.output_tokens\"') FROM spans"
        row = conn.execute(f"{quoted} WHERE span_id = ?", ("a" * 16,)).fetchone()
        assert row[0] == 17550
        # And this is the footgun the columns exist to retire: unquoted, SQLite reads
        # the dot as navigation into an object that isn't there and returns NULL with
        # no error at all.
        unquoted = "SELECT json_extract(attrs_json, '$.usage.output_tokens') FROM spans"
        assert conn.execute(f"{unquoted} WHERE span_id = ?", ("a" * 16,)).fetchone()[0] is None


def test_promoted_columns_are_added_to_a_database_that_predates_them():
    with _TelemetryEnv():
        # A groom.db from before the columns shipped. CREATE TABLE IF NOT EXISTS is a
        # no-op on it, so only the ALTER in _migrate can rescue it.
        legacy = sqlite3.connect(store.db_path())
        legacy.execute(
            "CREATE TABLE spans (span_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL,"
            " parent_id TEXT NOT NULL DEFAULT '', run_id TEXT NOT NULL DEFAULT '',"
            " workflow TEXT NOT NULL DEFAULT '', repo TEXT NOT NULL DEFAULT '',"
            " branch TEXT NOT NULL DEFAULT '', node TEXT NOT NULL DEFAULT '',"
            " name TEXT NOT NULL DEFAULT '', start_ts REAL NOT NULL, end_ts REAL NOT NULL,"
            " status TEXT NOT NULL DEFAULT 'UNSET', attrs_json TEXT NOT NULL DEFAULT '{}')"
        )
        legacy.execute(
            "INSERT INTO spans (span_id, trace_id, start_ts, end_ts) VALUES ('old', 't', 1, 2)"
        )
        legacy.commit()
        legacy.close()

        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [{"name": "agent_turn", "node": "plan-qa", "span_id": "c" * 16,
                      "numbers": _TURN}]
                )
            )
        )
        rows = _columns()
        assert rows["c" * 16]["output_tokens"] == 17550
        # The pre-existing row keeps NULL rather than needing a backfill; retention
        # ages it out on its own.
        assert rows["old"]["output_tokens"] is None


def _turn(node: str, work_id: str, cost: float, span_id: str) -> dict:
    return {
        "name": "agent_turn", "node": node, "span_id": span_id,
        "labels": {"work_id": work_id},
        "numbers": {"total_cost_usd": cost, "duration_ms": 60000},
    }


def test_node_costs_totals_agent_spend_and_exposes_the_rework_ratio():
    with _TelemetryEnv():
        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [
                        # A looping gate: three turns spread over two stories.
                        _turn("plan-qa", "story-a", 2.0, "01" * 8),
                        _turn("plan-qa", "story-a", 2.0, "02" * 8),
                        _turn("plan-qa", "story-b", 2.0, "03" * 8),
                        # A node that ran once per story.
                        _turn("implement-plan", "story-a", 1.0, "04" * 8),
                        _turn("implement-plan", "story-b", 1.0, "05" * 8),
                        # A node span wrapping the turns. It must not be counted, or
                        # every figure doubles.
                        {"name": "qa", "node": "qa", "span_id": "06" * 8},
                    ]
                )
            )
        )
        rows = {row["node"]: row for row in store.node_costs()}
        assert set(rows) == {"plan-qa", "implement-plan"}

        assert rows["plan-qa"]["turns"] == 3
        assert rows["plan-qa"]["cost_usd"] == 6.0
        assert rows["plan-qa"]["minutes"] == 3.0
        # The rework signal: three turns across two stories.
        assert rows["plan-qa"]["turns_per_work_id"] == 1.5
        assert rows["implement-plan"]["turns_per_work_id"] == 1.0
        # Share is of total agent spend, so the two nodes account for all of it.
        assert rows["plan-qa"]["share"] == 0.75
        assert rows["implement-plan"]["share"] == 0.25


def test_node_costs_reports_how_many_turns_actually_priced_themselves():
    """codex reports no money under subscription auth, so a mixed run's `share` is a
    fraction of only the turns that priced themselves. Counting them is what stops a
    codex-heavy node from reading as free."""
    with _TelemetryEnv():
        paid = _turn("plan-qa", "story-a", 4.0, "08" * 8)
        free = {
            "name": "agent_turn", "node": "implement-plan", "span_id": "09" * 8,
            "labels": {"work_id": "story-a", "backend": "codex"},
            "numbers": {"duration_ms": 120000},
        }
        paid["labels"] = {**paid["labels"], "backend": "claude"}
        store.insert_spans(otlp.parse_traces(_trace_request([paid, free])))

        rows = {row["node"]: row for row in store.node_costs()}
        assert rows["plan-qa"]["cost_turns"] == 1
        assert rows["plan-qa"]["backends"] == "claude"
        # The unpriced turn is counted and timed, but contributes no spend — and is
        # NOT silently folded in as 0.0, which would make it look free rather than
        # unmeasured.
        assert rows["implement-plan"]["turns"] == 1
        assert rows["implement-plan"]["cost_turns"] == 0
        assert rows["implement-plan"]["cost_usd"] is None
        assert rows["implement-plan"]["minutes"] == 2.0
        assert rows["implement-plan"]["backends"] == "codex"


def test_node_costs_counts_turns_that_priced_themselves_at_exactly_zero():
    """The failure a NULL check does not catch.

    opencode reports real money through OpenRouter and a literal 0 through a
    subscription provider. A NULL is excluded from the SUM and shows as a gap; a zero
    is summed, so a run that spent forty minutes totals $0.00 and looks complete.
    """
    with _TelemetryEnv():
        free_looking = {
            "name": "agent_turn", "node": "implement-plan", "span_id": "0a" * 8,
            "labels": {"work_id": "story-a", "backend": "opencode"},
            "numbers": {"total_cost_usd": 0.0, "usage.output_tokens": 905,
                        "duration_ms": 1800000},
        }
        store.insert_spans(otlp.parse_traces(_trace_request([free_looking])))
        row = store.node_costs()[0]
        # It is counted as priced — the harness did report a number — and *also*
        # counted as suspect, which is what lets the total say how much of itself
        # is real instead of asserting the run was free.
        assert row["cost_turns"] == 1
        assert row["zero_cost_turns"] == 1
        assert row["cost_usd"] == 0.0


def test_a_zero_cost_turn_that_spent_no_tokens_is_not_flagged():
    """An empty turn really did cost nothing. Flagging it would cry wolf on every run."""
    with _TelemetryEnv():
        empty = {
            "name": "agent_turn", "node": "noop", "span_id": "0b" * 8,
            "labels": {"work_id": "story-a", "backend": "opencode"},
            "numbers": {"total_cost_usd": 0.0, "usage.output_tokens": 0},
        }
        store.insert_spans(otlp.parse_traces(_trace_request([empty])))
        assert store.node_costs()[0]["zero_cost_turns"] == 0


def test_node_costs_reads_spans_ingested_before_the_columns_existed():
    with _TelemetryEnv():
        store.insert_spans(
            otlp.parse_traces(_trace_request([_turn("plan-qa", "story-a", 3.0, "07" * 8)]))
        )
        # Blank the promoted columns, leaving attrs_json — exactly the shape of every
        # row already in a collector database when this migration lands. Without the
        # COALESCE fallback the aggregate would report the run as free.
        conn = store._connection()
        conn.execute("UPDATE spans SET total_cost_usd = NULL, duration_ms = NULL")
        conn.commit()

        row = store.node_costs()[0]
        assert row["cost_usd"] == 3.0 and row["minutes"] == 1.0


def test_prune_expires_liveness_counters_sooner_than_diagnostic_metrics():
    with _TelemetryEnv():
        # Two days old: inside the 14-day metric window, outside the 1-day liveness one.
        now = 10 * 86400
        old = now - 2 * 86400
        store.insert_metrics(
            [
                {"run_id": "r", "name": "workhorse.run.heartbeat", "ts": old, "value": 1},
                {"run_id": "r", "name": "workhorse.turn.heartbeat", "ts": old, "value": 1},
                # A gauge: its history is how a wedged turn is diagnosed, so it keeps
                # the full window.
                {"run_id": "r", "name": "workhorse.turn.idle_s", "ts": old, "value": 42},
                # A fresh beat must survive regardless — this is the row live_status reads.
                {"run_id": "r", "name": "workhorse.run.heartbeat", "ts": now - 60, "value": 2},
            ]
        )
        store.prune(retention_days=14, now=now)
        kept = store._connection().execute(
            "SELECT name, ts FROM metrics ORDER BY name, ts"
        ).fetchall()
        assert [(row["name"], row["ts"]) for row in kept] == [
            ("workhorse.run.heartbeat", now - 60),
            ("workhorse.turn.idle_s", old),
        ]


def test_liveness_retention_never_outlives_the_table_wide_window():
    with _TelemetryEnv():
        now = 10 * 86400
        store.insert_metrics(
            [{"run_id": "r", "name": "workhorse.run.heartbeat", "ts": now - 7200, "value": 1}]
        )
        # A retention shorter than the liveness window must still win; the liveness
        # rule may only ever delete more, never keep a row the table-wide sweep drops.
        store.prune(retention_days=0.01, now=now)
        assert store._connection().execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 0


def test_run_summaries_count_spans_and_errors_without_claiming_liveness():
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
        # now near the fixture's own (epoch-small) timestamps, so the recent-window
        # bound in run_summaries includes them rather than filtering to wall-clock.
        summary = store.run_summaries(now=200.0)[0]
        assert summary["run_id"] == "run-1"
        assert summary["error_count"] == 1 and summary["span_count"] == 2
        # A root span is history, not a liveness verdict: a resumed run reuses its
        # run_id, so "a run:* span exists" would mark it dead forever.
        assert "finished" not in summary


def test_prune_drops_only_old_rows():
    with _TelemetryEnv():
        store.insert_spans(
            otlp.parse_traces(_trace_request([{"name": "old", "start": 10, "end": 20}]))
        )
        removed = store.prune(retention_days=1, now=20 + 2 * 86400)
        assert removed == 1 and store.query_spans() == []


# --------------------------------------------------------------------------- #
# test-run telemetry: not collected, and evicted where it already landed
# --------------------------------------------------------------------------- #
def test_run_dir_predicates_split_certain_test_dirs_from_merely_scratch_ones():
    # Certain: what the ingest path is allowed to drop silently.
    for certain in (
        "/tmp/pytest-of-gabriel/pytest-1/test_x0/runs/coder",
        "/home/me/repo/.workhorse-test/runs/coder-default",
    ):
        assert store.is_test_run_dir(certain) is True
        assert store.is_scratch_run_dir(certain) is True
    # A mkdtemp dir is a guess: purge-worthy, but never dropped at ingest.
    assert store.is_test_run_dir("/tmp/tmpab12cd34/runs/coder-default") is False
    assert store.is_scratch_run_dir("/tmp/tmpab12cd34/runs/coder-default") is True
    # A real run, and a hand-made directory that merely lives under /tmp.
    for real in ("/home/me/repo/.agents/runs/coder-ACME-1", "/tmp/scratch/runs/coder"):
        assert store.is_test_run_dir(real) is False
        assert store.is_scratch_run_dir(real) is False
    # No run dir on the record is not evidence of anything — leave it alone.
    assert store.is_test_run_dir("") is False and store.is_scratch_run_dir("") is False


def test_receivers_drop_test_run_telemetry_but_keep_real_runs():
    with _TelemetryEnv():
        client = _hermetic_client()
        try:
            for run_id, run_dir in (
                ("suite-run", "/tmp/pytest-of-me/pytest-3/test_flow0/runs/coder"),
                ("real-run", "/home/me/repo/.agents/runs/coder-ACME-1"),
            ):
                resource = {"run_id": run_id, "workflow": "coder", "run_dir": run_dir}
                assert client.post(
                    "/v1/traces",
                    content=_trace_request([{"name": "plan", "node": "plan"}], resource),
                    headers={"content-type": "application/x-protobuf"},
                ).status_code == 200
                assert client.post(
                    "/v1/logs",
                    content=_logs_request([{"body": "hi"}], resource),
                    headers={"content-type": "application/x-protobuf"},
                ).status_code == 200
                assert client.post(
                    "/v1/metrics",
                    content=_metrics_request(
                        "workhorse.run.heartbeat", run_id=run_id, run_dir=run_dir
                    ),
                    headers={"content-type": "application/x-protobuf"},
                ).status_code == 200
            assert [s["run_id"] for s in store.query_spans()] == ["real-run"]
            assert [r["run_id"] for r in store.query_logs()] == ["real-run"]
            assert store.live_status(now=2000.0)[0]["run_id"] == "real-run"
            assert len(store.live_status(now=2000.0)) == 1
        finally:
            client.__exit__(None, None, None)


def test_purge_test_runs_evicts_by_run_dir_across_all_three_tables():
    with _TelemetryEnv():
        suite = {"run_id": "suite-run", "workflow": "coder", "run_dir": "/tmp/pytest-of-me/t0/r"}
        real = {"run_id": "real-run", "workflow": "coder", "run_dir": "/home/me/repo/.agents/runs/x"}
        for resource in (suite, real):
            store.insert_spans(
                otlp.parse_traces(_trace_request([{"name": "plan", "node": "plan"}], resource))
            )
            store.insert_logs(otlp.parse_logs(_logs_request([{"body": "hi"}], resource)))
            # Metrics carry no run_dir column, so they can only be evicted by the
            # run_id the spans/logs identified — which is exactly what this pins.
            store.insert_metrics(
                otlp.parse_metrics(
                    _metrics_request("workhorse.run.heartbeat", run_id=resource["run_id"])
                )
            )
        assert store.test_run_ids() == {"suite-run"}

        preview = store.purge_test_runs(dry_run=True)
        assert preview == {"runs": 1, "spans": 1, "metrics": 1, "logs": 1}
        assert len(store.query_spans()) == 2  # dry run deleted nothing

        assert store.purge_test_runs() == preview
        assert [s["run_id"] for s in store.query_spans()] == ["real-run"]
        assert [r["run_id"] for r in store.query_logs()] == ["real-run"]
        assert store.test_run_ids() == set()
        # Nothing left to do: a second pass is a no-op, not an error.
        assert store.purge_test_runs()["runs"] == 0


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


def test_a_drain_iterating_over_its_worklist_is_not_churn():
    """Regression: okf-builder's drain paged as CHURN on its fifth item.

    ``select_item -> investigate -> record -> select_item`` re-completes the same
    nodes once per worklist item, and the pyflow engine has no gas tank to refuel,
    so the old rule counted every healthy iteration and never reset. The labels
    say which item each iteration was for; a changing ``work_id`` is the progress
    the refuel counter used to report.
    """
    with _TelemetryEnv(), patch.dict(os.environ, {"GROOM_CHURN_REPEATS": "3"}):
        for index, target in enumerate(["cli:yin", "cli:yin-preflight", "server:api", "env:local"]):
            drain = otlp.parse_traces(
                _trace_request(
                    [
                        {
                            "name": node,
                            "node": node,
                            "seq": index * 3 + offset,
                            "labels": {"work_id": target, "progress": f"{index}/9"},
                        }
                        for offset, node in enumerate(["select_item", "investigate", "record"])
                    ]
                )
            )
            assert alerts.ingest_spans(drain, now=10.0 + index) == []


def test_churn_still_fires_when_the_same_work_repeats():
    """The condition the rule exists for, now stated precisely: the same node
    completing again and again for the SAME unit of work."""
    with _TelemetryEnv(), patch.dict(os.environ, {"GROOM_CHURN_REPEATS": "3"}):
        stuck_item = [
            {"name": "investigate", "node": "investigate", "seq": seq,
             "labels": {"work_id": "server:api", "progress": "2/16"}}
            for seq in range(3)
        ]
        assert alerts.ingest_spans(otlp.parse_traces(_trace_request(stuck_item[:1])), now=10.0) == []
        assert alerts.ingest_spans(otlp.parse_traces(_trace_request(stuck_item[1:2])), now=11.0) == []
        fired = alerts.ingest_spans(otlp.parse_traces(_trace_request(stuck_item[2:])), now=12.0)
        assert [a.rule for a in fired] == ["CHURN"]
        assert "on the same work" in fired[0].message
        # ...and it retires as soon as the run moves to the next item.
        moved_on = _trace_request(
            [{"name": "investigate", "node": "investigate", "seq": 9,
              "labels": {"work_id": "env:local", "progress": "3/16"}}]
        )
        alerts.ingest_spans(otlp.parse_traces(moved_on), now=13.0)
        assert "CHURN" not in state.RUNS["run-1"].fired


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


def test_stall_retires_when_the_run_emits_again_and_can_refire():
    """Regression: a host that idle-slept past the stall window left its run
    badged STALL forever, however healthily it resumed.

    STALL asserts the process is gone. Anything arriving under the run's id
    refutes that, so the page is false rather than merely old — and ``fired`` is
    what the dashboard renders. A run that goes quiet again pages again.
    """
    with _TelemetryEnv(), patch.dict(os.environ, {"GROOM_STALL_MIN": "90"}):
        spans = otlp.parse_traces(_trace_request([{"name": "plan", "node": "plan"}]))
        alerts.ingest_spans(spans, now=1000.0)
        woke = 1000.0 + 100 * 60
        assert [a.rule for a in alerts.check_time_rules(now=woke)] == ["STALL"]

        # The laptop wakes and the run — never actually dead — beats again.
        alerts.ingest_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat")), now=woke
        )
        assert "STALL" not in state.RUNS["run-1"].fired
        assert alerts.check_time_rules(now=woke + 60) == []

        # Genuinely silent this time: the rule is armed again, not spent.
        assert [a.rule for a in alerts.check_time_rules(now=woke + 91 * 60)] == ["STALL"]


def test_stuck_retires_when_the_node_finally_closes():
    """STUCK says a node is open past the threshold. When it closes the claim is
    false, not stale — so the badge goes with it."""
    with _TelemetryEnv(), patch.dict(
        os.environ, {"GROOM_STALL_MIN": "90", "GROOM_STUCK_MIN": "75"}
    ):
        now = 1000.0
        for name, value in (("workhorse.node.active", 1), ("workhorse.node.elapsed_s", 76 * 60)):
            alerts.ingest_metrics(
                otlp.parse_metrics(
                    _metrics_request(name, value=value, node="investigate", gauge=True)
                ),
                now=now,
            )
        assert [a.rule for a in alerts.check_time_rules(now=now)] == ["STUCK"]

        alerts.ingest_metrics(
            otlp.parse_metrics(
                _metrics_request("workhorse.node.active", value=0, node="investigate", gauge=True)
            ),
            now=now + 60,
        )
        assert "STUCK" not in state.RUNS["run-1"].fired


def test_turn_heartbeat_suppresses_stall_during_a_long_agent_turn():
    """Regression: a legitimately long agent turn used to page as a STALL.

    Its node span cannot export until it ends, and it is not a cap sleep, so the
    run went silent by construction and every rule read that as a hang. The turn
    heartbeat is the missing liveness proof.
    """
    with _TelemetryEnv(), patch.dict(os.environ, {"GROOM_STALL_MIN": "90"}):
        spans = otlp.parse_traces(_trace_request([{"name": "plan", "node": "plan"}]))
        alerts.ingest_spans(spans, now=1000.0)
        # A long turn starts: no spans will arrive until it finishes, but the
        # stream loop keeps beating.
        for minute in range(0, 200, 5):
            alerts.ingest_metrics(
                otlp.parse_metrics(_metrics_request("workhorse.turn.heartbeat")),
                now=1000.0 + minute * 60,
            )
        # Over 3 hours after the last span, and still not a stall.
        assert alerts.check_time_rules(now=1000.0 + 195 * 60) == []


def test_run_heartbeat_suppresses_stall_for_a_buffered_script_node():
    """A script node runs as a captured subprocess: no stream, so no turn
    heartbeat. The run-level heartbeat is its only liveness signal."""
    with _TelemetryEnv(), patch.dict(os.environ, {"GROOM_STALL_MIN": "90"}):
        alerts.ingest_spans(
            otlp.parse_traces(_trace_request([{"name": "prepare", "node": "prepare"}])),
            now=1000.0,
        )
        alerts.ingest_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat")),
            now=1000.0 + 100 * 60,
        )
        assert alerts.check_time_rules(now=1000.0 + 150 * 60) == []


def test_stuck_fires_when_alive_but_parked_in_one_node():
    """The case a script-heavy workflow actually hits: the process is fine, the
    node just never finishes. Invisible to the trace — that span never exports."""
    with _TelemetryEnv(), patch.dict(
        os.environ, {"GROOM_STALL_MIN": "90", "GROOM_STUCK_MIN": "75"}
    ):
        now = 1000.0
        alerts.ingest_metrics(
            otlp.parse_metrics(
                _metrics_request("workhorse.node.active", value=1, node="select_item", gauge=True)
            ),
            now=now,
        )
        alerts.ingest_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat")), now=now
        )
        # 74 minutes in the node: not yet.
        alerts.ingest_metrics(
            otlp.parse_metrics(
                _metrics_request(
                    "workhorse.node.elapsed_s", value=74 * 60, node="select_item", gauge=True
                )
            ),
            now=now,
        )
        assert alerts.check_time_rules(now=now) == []
        # 76 minutes: alive, heartbeating, and going nowhere.
        alerts.ingest_metrics(
            otlp.parse_metrics(
                _metrics_request(
                    "workhorse.node.elapsed_s", value=76 * 60, node="select_item", gauge=True
                )
            ),
            now=now,
        )
        fired = alerts.check_time_rules(now=now)
        assert [a.rule for a in fired] == ["STUCK"]
        assert "select_item" in fired[0].message
        # Dedupes: one page per rule per run.
        assert alerts.check_time_rules(now=now + 60) == []


def test_node_active_gauge_tracks_where_the_run_is_and_clears_on_completion():
    with _TelemetryEnv():
        alerts.ingest_metrics(
            otlp.parse_metrics(
                _metrics_request("workhorse.node.active", value=1, node="prepare", gauge=True)
            ),
            now=1000.0,
        )
        assert state.RUNS["run-1"].current_node == "prepare"
        alerts.ingest_metrics(
            otlp.parse_metrics(
                _metrics_request("workhorse.node.active", value=0, node="prepare", gauge=True)
            ),
            now=1001.0,
        )
        assert state.RUNS["run-1"].current_node == ""


def test_a_stale_zero_does_not_blank_the_node_now_running():
    """Gauges re-export their last value, so a 0 for an already-superseded node
    can arrive after the next node has opened. It must not clear the pointer."""
    with _TelemetryEnv():
        for name, value, node in (
            ("workhorse.node.active", 1, "prepare"),
            ("workhorse.node.active", 1, "select_item"),
            ("workhorse.node.active", 0, "prepare"),
        ):
            alerts.ingest_metrics(
                otlp.parse_metrics(_metrics_request(name, value=value, node=node, gauge=True)),
                now=1000.0,
            )
        assert state.RUNS["run-1"].current_node == "select_item"


def test_live_status_reports_the_open_node_that_has_no_span():
    """The whole point: a run parked in a node has NO row in `spans` for it (the
    span writes on completion), yet live_status still says where it is."""
    with _TelemetryEnv():
        store.insert_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat", node="select_item"))
        )
        store.insert_metrics(
            otlp.parse_metrics(
                _metrics_request(
                    "workhorse.node.elapsed_s", value=1800.0, node="select_item", gauge=True
                )
            )
        )
        # No span for select_item exists — and never will while it hangs.
        assert store.query_spans(node="select_item") == []
        rows = store.live_status(now=2000.0)
        assert len(rows) == 1
        assert rows[0]["node"] == "select_item"
        assert rows[0]["node_elapsed_s"] == 1800.0
        assert rows[0]["alive"] is True


def test_live_status_marks_a_run_dead_once_the_heartbeat_stops():
    with _TelemetryEnv():
        store.insert_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat", node="investigate"))
        )
        # Heartbeat ts is 2000; well past the liveness window.
        rows = store.live_status(now=2000.0 + store.LIVE_AFTER_S + 60)
        assert rows[0]["alive"] is False
        assert rows[0]["node"] == "investigate"


def test_live_run_ids_are_the_ones_beating_now():
    """The durable answer to the only liveness question groom asks. It comes from
    the store, not the hot cache, so a groom that just restarted does not report
    every live run as stopped until each one's next export lands."""
    with _TelemetryEnv():
        store.insert_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat", node="impl"))
        )
        assert store.live_run_ids(now=2000.0) == {"run-1"}
        assert store.live_run_ids(now=2000.0 + store.LIVE_AFTER_S + 60) == set()


def test_live_status_uses_only_the_newest_point_per_metric():
    with _TelemetryEnv():
        for ts_node in ("prepare", "select_item"):
            store.insert_metrics(
                otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat", node=ts_node))
            )
        # Both points share a timestamp in the fixture; make the second newer.
        store._connection().execute(
            "UPDATE metrics SET ts = 3000 WHERE json_extract(attrs_json,'$.node') = 'select_item'"
        )
        rows = store.live_status(now=3000.0)
        assert rows[0]["node"] == "select_item"


def test_run_dir_survives_decode_and_storage():
    """A span must lead back to its artifacts (prompt.md / output.json) in one
    hop — that join is what a hosted trace backend cannot do."""
    with _TelemetryEnv():
        spans = otlp.parse_traces(
            _trace_request(
                [{"name": "prepare", "node": "prepare"}],
                resource={"run_id": "run-1", "workflow": "okf", "run_dir": "/runs/okf-1"},
            )
        )
        assert spans[0]["run_dir"] == "/runs/okf-1"
        store.insert_spans(spans)
        assert store.query_spans(run="run-1")[0]["run_dir"] == "/runs/okf-1"


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


def test_a_resumed_run_clears_the_previous_sessions_terminal():
    """``--resume-run`` reuses the run_id, and a root span only exports when it
    ENDS — so there is no "new session started" event. The newer signal itself is
    the evidence, and it has to undo the verdict or the run stays dead forever."""
    with _TelemetryEnv():
        root = otlp.parse_traces(
            _trace_request([{"name": "run:coder", "terminal": "interrupted", "end": 100.0}])
        )
        alerts.ingest_spans(root, now=100.0)
        run = state.RUNS["run-1"]
        assert (run.terminal, run.terminal_ts) == ("interrupted", 100.0)
        run.fired.add("STALL")

        # A single beat from the resumed process, stamped after that root span.
        alerts.ingest_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat", ts=200.0)),
            now=200.0,
        )
        assert (run.terminal, run.terminal_ts) == ("", 0.0)
        assert run.fired == set()  # a new session re-arms every rule


def test_a_signal_older_than_the_terminal_does_not_revive_the_run():
    """The inverse guard: telemetry that predates the root span is the same
    session's backlog, not a resume, and must leave the verdict standing."""
    with _TelemetryEnv():
        root = otlp.parse_traces(
            _trace_request([{"name": "run:coder", "terminal": "terminal", "end": 100.0}])
        )
        alerts.ingest_spans(root, now=100.0)
        alerts.ingest_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat", ts=50.0)),
            now=100.0,
        )
        assert state.RUNS["run-1"].terminal == "terminal"


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


def test_traces_search_endpoint_returns_json_rows():
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
        # A heartbeat inside the live window: the pane shows connected runs, so a
        # run with span history alone is history, not a row (see the test below).
        store.insert_metrics(
            otlp.parse_metrics(_metrics_request("workhorse.run.heartbeat", ts=now))
        )
        client = _hermetic_client()
        try:
            resp = client.get("/traces", params={"status": "ERROR"})
        finally:
            client.__exit__(None, None, None)
        body = resp.json()
        nodes = [row["node"] for row in body["spans"]]
        assert nodes == ["build"]  # the status filter applied; "plan" was OK
        assert body["spans"][0]["status"] == "ERROR"
        # The summary strip rides along with the spans, so the pane needs one fetch.
        assert [run["run_id"] for run in body["runs"]] == ["run-1"]


def test_traces_endpoint_hides_runs_that_are_not_connected_now():
    import time as _time

    now = _time.time()
    with _TelemetryEnv():
        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [{"name": "plan", "node": "plan", "start": now - 20, "end": now - 19}],
                    resource={"run_id": "ended-run", "workflow": "coder"},
                )
            )
        )
        store.insert_spans(
            otlp.parse_traces(
                _trace_request(
                    [{"name": "plan", "node": "plan", "start": now - 10, "end": now - 9}],
                    resource={"run_id": "live-run", "workflow": "coder"},
                )
            )
        )
        # Only one of the two is still beating. Both have span history, which is
        # exactly the distinction the pane could not make before.
        store.insert_metrics(
            otlp.parse_metrics(
                _metrics_request("workhorse.run.heartbeat", run_id="live-run", ts=now)
            )
        )
        store.insert_metrics(
            otlp.parse_metrics(
                _metrics_request(
                    "workhorse.run.heartbeat",
                    run_id="ended-run",
                    ts=now - store.LIVE_AFTER_S - 600,
                )
            )
        )
        client = _hermetic_client()
        try:
            default = client.get("/traces").json()
            everything = client.get("/traces", params={"show_ended": "1"}).json()
            named = client.get("/traces", params={"run": "ended-run"}).json()
        finally:
            client.__exit__(None, None, None)

        # Default: the connected run only, and its spans only.
        assert [run["run_id"] for run in default["runs"]] == ["live-run"]
        assert {row["run_id"] for row in default["spans"]} == {"live-run"}
        # The toggle is the way back to history.
        assert {run["run_id"] for run in everything["runs"]} == {"live-run", "ended-run"}
        assert {row["run_id"] for row in everything["spans"]} == {"live-run", "ended-run"}
        # Naming a run is asking for that run, finished or not — no toggle needed.
        assert [run["run_id"] for run in named["runs"]] == ["ended-run"]
        assert {row["run_id"] for row in named["spans"]} == {"ended-run"}


def test_traces_view_carries_untrusted_values_verbatim():
    # No escaping here any more, and that is the point: the pane is JSON the
    # browser renders as text nodes, so a run id that looks like markup stays a
    # run id that looks like markup instead of being mangled on the way out. The
    # escaping this replaced existed because the value was concatenated into HTML.
    view = projection.traces_view(
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
        connected_only=False,
    )
    assert view["spans"][0]["run_id"] == "<img src=x>"
    assert view["spans"][0]["node"] == "<script>alert(1)</script>"


# ── Logs (/v1/logs) ────────────────────────────────────────────────────────────
#
# Logs are the third OTLP leg and the one that finally makes script nodes legible:
# they used to run as child processes whose stdout was consumed whole as JSON and
# whose stderr surfaced only on failure, so their diagnostics were unrecoverable
# after the fact. workhorse now runs them in-process, so their records arrive here
# on the engine's own resource.


def test_parse_logs_extracts_identity_node_and_body():
    records = otlp.parse_logs(
        _logs_request([{"body": "picked item 3", "attrs": {"node": "select_item"}}])
    )
    assert len(records) == 1
    got = records[0]
    assert got["run_id"] == "run-1"
    assert got["workflow"] == "okf-builder"
    assert got["body"] == "picked item 3"
    # node comes from the record attribute, not the trace context: workhorse never
    # makes its node spans current, so trace_id is zeroes and only this correlates.
    assert got["node"] == "select_item"
    # run_dir rides the resource, so a log line leads back to prompt.md/output.json.
    assert got["run_dir"] == "/runs/r1"


def test_severity_is_normalized_to_stdlib_names_not_the_sdk_text():
    """The SDK stamps Python's WARNING with severity_text "WARN". Storing that
    verbatim made `groom logs --level WARNING` match nothing at all, silently,
    because the filter compares against the stdlib names. The number wins."""
    records = otlp.parse_logs(
        _logs_request([{"severity": 13, "severity_text": "WARN", "body": "careful"}])
    )
    assert records[0]["severity"] == "WARNING"


def test_severity_falls_back_to_text_when_the_number_is_unset():
    records = otlp.parse_logs(
        _logs_request([{"severity": 0, "severity_text": "info", "body": "x"}])
    )
    assert records[0]["severity"] == "INFO"


def test_logs_roundtrip_and_query_filters():
    with _TelemetryEnv():
        store.insert_logs(
            otlp.parse_logs(
                _logs_request(
                    [
                        {"body": "starting", "severity": 9, "ts": 10,
                         "attrs": {"node": "prepare"}},
                        {"body": "over budget", "severity": 13, "ts": 11,
                         "attrs": {"node": "select_item"}},
                        {"body": "exploded", "severity": 17, "ts": 12,
                         "attrs": {"node": "select_item"}},
                    ]
                )
            )
        )
        assert len(store.query_logs()) == 3
        assert {r["body"] for r in store.query_logs(node="select_item")} == {
            "over budget", "exploded"
        }
        # level is a FLOOR, not equality — being shown warnings but not errors
        # would be the opposite of useful.
        assert {r["body"] for r in store.query_logs(level="WARNING")} == {
            "over budget", "exploded"
        }
        assert {r["body"] for r in store.query_logs(level="ERROR")} == {"exploded"}
        assert [r["body"] for r in store.query_logs(contains="budget")] == ["over budget"]
        assert store.query_logs(run="nope") == []


def test_logs_receiver_stores_and_returns_200():
    with _TelemetryEnv():
        client = _hermetic_client()
        try:
            response = client.post(
                "/v1/logs",
                content=_logs_request([{"body": "hi", "attrs": {"node": "prepare"}}]),
                headers={"content-type": "application/x-protobuf"},
            )
            # OTLP/HTTP defines success as 200; Litestar's POST default is 201.
            assert response.status_code == 200
            assert [r["body"] for r in store.query_logs()] == ["hi"]
        finally:
            client.__exit__(None, None, None)


def test_logs_receiver_rejects_an_undecodable_body():
    with _TelemetryEnv():
        client = _hermetic_client()
        try:
            response = client.post(
                "/v1/logs",
                content=b"not-a-protobuf",
                headers={"content-type": "application/x-protobuf"},
            )
            assert response.status_code == 400
        finally:
            client.__exit__(None, None, None)


def test_logs_prune_on_their_own_shorter_window():
    """Logs are one row per line rather than one per node visit, so they outgrow
    spans by orders of magnitude; holding them for the span retention would let a
    few chatty week-long runs dominate the file."""
    with _TelemetryEnv():
        now = 100 * 86400
        store.insert_logs(otlp.parse_logs(_logs_request([{"body": "old", "ts": now - 5 * 86400}])))
        store.insert_logs(otlp.parse_logs(_logs_request([{"body": "new", "ts": now - 3600}])))
        # Span retention (14d) would keep both; the log window (3d) must not.
        store.prune(retention_days=14, now=now)
        assert [r["body"] for r in store.query_logs()] == ["new"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
