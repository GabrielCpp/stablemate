"""Decode standard OTLP/HTTP protobuf export requests into plain dicts."""

from __future__ import annotations

import logging
import threading
from collections import Counter
from typing import Any

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

logger = logging.getLogger(__name__)

_dropped = Counter()
_dropped_lock = threading.Lock()


def dropped_no_run_id() -> dict[str, int]:
    """A snapshot of :data:`_dropped` — what has been refused at the door, by signal."""
    with _dropped_lock:
        return dict(_dropped)


def _note_dropped(signal: str, count: int) -> None:
    """Count a batch's refusals and say so once, rather than once per record."""
    if not count:
        return
    with _dropped_lock:
        _dropped[signal] += count
        total = _dropped[signal]
    logger.warning(
        "groom: dropped %d %s record(s) carrying no run_id (%d so far); the producer's"
        " OTel resource is missing the run_id attribute",
        count, signal, total,
    )


_STATUS_NAMES = {0: "UNSET", 1: "OK", 2: "ERROR"}
_NANOS = 1e9

_SEVERITY_TIERS = (
    (21, "FATAL"), (17, "ERROR"), (13, "WARNING"), (9, "INFO"), (5, "DEBUG"), (1, "TRACE"),
)


def _any_value(value: Any) -> Any:
    """One protobuf ``AnyValue`` → the equivalent plain Python value."""
    kind = value.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [_any_value(v) for v in value.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _any_value(kv.value) for kv in value.kvlist_value.values}
    if kind == "bytes_value":
        return value.bytes_value.hex()
    return getattr(value, kind)


def _attrs(key_values: Any) -> dict[str, Any]:
    return {kv.key: _any_value(kv.value) for kv in key_values}


def _int_or_none(value: Any) -> int | None:
    """A resource attribute coerced to int, or None when absent/unparseable — so a missing pid stays distinguishable from pid 0 rather than defaulting to a number."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_traces(body: bytes) -> list[dict[str, Any]]:
    """Decode an ``ExportTraceServiceRequest`` into one dict per span: identity + timing columns ready for the spans table, plus an ``attrs`` dict (span attributes, events, status message) the store JSON-encodes."""
    request = ExportTraceServiceRequest.FromString(body)
    dropped = 0
    records: list[dict[str, Any]] = []
    for resource_spans in request.resource_spans:
        resource = _attrs(resource_spans.resource.attributes)
        run_id = str(resource.get("run_id", ""))
        if not run_id:
            dropped += sum(len(scope.spans) for scope in resource_spans.scope_spans)
            continue
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                attrs = _attrs(span.attributes)
                attrs["events"] = [
                    {
                        "name": event.name,
                        "ts": event.time_unix_nano / _NANOS,
                        "attrs": _attrs(event.attributes),
                    }
                    for event in span.events
                ]
                if span.status.message:
                    attrs["status_message"] = span.status.message
                records.append(
                    {
                        "trace_id": span.trace_id.hex(),
                        "span_id": span.span_id.hex(),
                        "parent_id": span.parent_span_id.hex(),
                        "run_id": run_id,
                        "workflow": str(resource.get("workflow", "")),
                        "repo": str(resource.get("repo", "")),
                        "branch": str(resource.get("branch", "")),
                        "run_dir": str(resource.get("run_dir", "")),
                        "workspace": str(resource.get("workspace", "")),
                        "pid": _int_or_none(resource.get("process.pid")),
                        "resume_generation": _int_or_none(
                            resource.get("workhorse.resume_generation")
                        ),
                        "node": str(attrs.get("workhorse.node", "") or span.name),
                        "name": span.name,
                        "start_ts": span.start_time_unix_nano / _NANOS,
                        "end_ts": span.end_time_unix_nano / _NANOS,
                        "status": _STATUS_NAMES.get(span.status.code, "UNSET"),
                        "attrs": attrs,
                    }
                )
    _note_dropped("traces", dropped)
    return records


def _severity(number: int, text: str) -> str:
    """The record's level name, normalized to a stdlib logging level."""
    for floor, name in _SEVERITY_TIERS:
        if number >= floor:
            return name
    return text.upper() if text else "UNSET"


def parse_logs(body: bytes) -> list[dict[str, Any]]:
    """Decode an ``ExportLogsServiceRequest`` into one dict per log record."""
    request = ExportLogsServiceRequest.FromString(body)
    dropped = 0
    records: list[dict[str, Any]] = []
    for resource_logs in request.resource_logs:
        resource = _attrs(resource_logs.resource.attributes)
        run_id = str(resource.get("run_id", ""))
        if not run_id:
            dropped += sum(len(scope.log_records) for scope in resource_logs.scope_logs)
            continue
        for scope_logs in resource_logs.scope_logs:
            for record in scope_logs.log_records:
                attrs = _attrs(record.attributes)
                ts = record.time_unix_nano or record.observed_time_unix_nano
                records.append(
                    {
                        "run_id": run_id,
                        "workflow": str(resource.get("workflow", "")),
                        "run_dir": str(resource.get("run_dir", "")),
                        "node": str(attrs.get("node", "")),
                        "logger": str(attrs.get("logger.name", "") or scope_logs.scope.name),
                        "severity": _severity(record.severity_number, record.severity_text),
                        "body": str(_any_value(record.body) or ""),
                        "ts": ts / _NANOS,
                        "trace_id": record.trace_id.hex(),
                        "attrs": attrs,
                    }
                )
    _note_dropped("logs", dropped)
    return records


def _points(metric: Any) -> Any:
    """The data points of the metric kinds workhorse emits (gauge/sum); other kinds (histogram etc.) are skipped rather than mis-read."""
    kind = metric.WhichOneof("data")
    if kind == "gauge":
        return metric.gauge.data_points
    if kind == "sum":
        return metric.sum.data_points
    return []


def parse_metrics(body: bytes) -> list[dict[str, Any]]:
    """Decode an ``ExportMetricsServiceRequest`` into one dict per data point."""
    request = ExportMetricsServiceRequest.FromString(body)
    dropped = 0
    records: list[dict[str, Any]] = []
    for resource_metrics in request.resource_metrics:
        resource = _attrs(resource_metrics.resource.attributes)
        run_id = str(resource.get("run_id", ""))
        if not run_id:
            dropped += sum(
                len(_points(metric))
                for scope in resource_metrics.scope_metrics
                for metric in scope.metrics
            )
            continue
        workflow = str(resource.get("workflow", ""))
        repo = str(resource.get("repo", ""))
        branch = str(resource.get("branch", ""))
        run_dir = str(resource.get("run_dir", ""))
        workspace = str(resource.get("workspace", ""))
        pid = _int_or_none(resource.get("process.pid"))
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                for point in _points(metric):
                    value = (
                        point.as_double
                        if point.WhichOneof("value") == "as_double"
                        else point.as_int
                    )
                    records.append(
                        {
                            "run_id": run_id,
                            "workflow": workflow,
                            "repo": repo,
                            "branch": branch,
                            "run_dir": run_dir,
                            "workspace": workspace,
                            "pid": pid,
                            "resume_generation": _int_or_none(resource.get("workhorse.resume_generation")),
                            "name": metric.name,
                            "ts": point.time_unix_nano / _NANOS,
                            "value": float(value),
                            "attrs": _attrs(point.attributes),
                        }
                    )
    _note_dropped("metrics", dropped)
    return records
