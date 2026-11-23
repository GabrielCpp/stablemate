"""One builder for the OTLP metric exports the groom tests post."""
from __future__ import annotations

from groom.otlp import ExportMetricsServiceRequest


def metrics_request(
    name: str,
    run_id: str = "run-1",
    value: float = 1,
    *,
    node: str | None = None,
    gauge: bool = False,
    ts: float = 2000.0,
    run_dir: str = "",
    workflow: str = "",
    attrs: dict[str, str] | None = None,
) -> bytes:
    """One metric point."""
    request = ExportMetricsServiceRequest()
    resource_metrics = request.resource_metrics.add()
    kv = resource_metrics.resource.attributes.add()
    kv.key, kv.value.string_value = "run_id", run_id
    if run_dir:
        kv = resource_metrics.resource.attributes.add()
        kv.key, kv.value.string_value = "run_dir", run_dir
    if workflow:
        kv = resource_metrics.resource.attributes.add()
        kv.key, kv.value.string_value = "workflow", workflow
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
    for key, attr_value in (attrs or {}).items():
        kv = point.attributes.add()
        kv.key, kv.value.string_value = key, attr_value
    point.time_unix_nano = int(ts * 1e9)
    return request.SerializeToString()
