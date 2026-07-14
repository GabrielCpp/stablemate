"""Decode standard OTLP/HTTP protobuf export requests into plain dicts.

groom speaks the real OTLP wire format (``opentelemetry-proto``) rather than a
private JSON shape so the workhorse producer can point the stock OTel SDK
exporter at it — and, symmetrically, at Jaeger/Tempo — with zero code change.
Only decoding lives here; storage is :mod:`groom.store`, rules are
:mod:`groom.alerts`.

Spans/metric points come out as flat dicts (see ``parse_traces`` /
``parse_metrics``) carrying the workhorse resource identity (run_id, workflow,
repo, branch) denormalized onto every record, so the store and the alert rules
never need to re-join resources.
"""

from __future__ import annotations

from typing import Any

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

_STATUS_NAMES = {0: "UNSET", 1: "OK", 2: "ERROR"}
_NANOS = 1e9


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


def parse_traces(body: bytes) -> list[dict[str, Any]]:
    """Decode an ``ExportTraceServiceRequest`` into one dict per span:
    identity + timing columns ready for the spans table, plus an ``attrs``
    dict (span attributes, events, status message) the store JSON-encodes.
    Raises on undecodable input — the receiver turns that into a 400."""
    request = ExportTraceServiceRequest.FromString(body)
    records: list[dict[str, Any]] = []
    for resource_spans in request.resource_spans:
        resource = _attrs(resource_spans.resource.attributes)
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
                        "run_id": str(resource.get("run_id", "")),
                        "workflow": str(resource.get("workflow", "")),
                        "repo": str(resource.get("repo", "")),
                        "branch": str(resource.get("branch", "")),
                        "node": str(attrs.get("workhorse.node", "") or span.name),
                        "name": span.name,
                        "start_ts": span.start_time_unix_nano / _NANOS,
                        "end_ts": span.end_time_unix_nano / _NANOS,
                        "status": _STATUS_NAMES.get(span.status.code, "UNSET"),
                        "attrs": attrs,
                    }
                )
    return records


def _points(metric: Any) -> Any:
    """The data points of the metric kinds workhorse emits (gauge/sum); other
    kinds (histogram etc.) are skipped rather than mis-read."""
    kind = metric.WhichOneof("data")
    if kind == "gauge":
        return metric.gauge.data_points
    if kind == "sum":
        return metric.sum.data_points
    return []


def parse_metrics(body: bytes) -> list[dict[str, Any]]:
    """Decode an ``ExportMetricsServiceRequest`` into one dict per data point."""
    request = ExportMetricsServiceRequest.FromString(body)
    records: list[dict[str, Any]] = []
    for resource_metrics in request.resource_metrics:
        resource = _attrs(resource_metrics.resource.attributes)
        run_id = str(resource.get("run_id", ""))
        workflow = str(resource.get("workflow", ""))
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
                            "name": metric.name,
                            "ts": point.time_unix_nano / _NANOS,
                            "value": float(value),
                            "attrs": _attrs(point.attributes),
                        }
                    )
    return records
