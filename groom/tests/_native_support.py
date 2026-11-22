from __future__ import annotations

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest


def node_active_export(
    run_id: str, run_dir: str, workspace: str, node: str = "review", activity: str = "", pid: int | None = None
) -> bytes:
    req = ExportMetricsServiceRequest()
    rm = req.resource_metrics.add()
    for key, val in (
        ("run_id", run_id), ("workflow", "coder"), ("repo", "acme"),
        ("branch", "main"), ("run_dir", run_dir), ("workspace", workspace),
    ):
        kv = rm.resource.attributes.add()
        kv.key, kv.value.string_value = key, val
    if pid is not None:
        kv = rm.resource.attributes.add()
        kv.key, kv.value.int_value = "process.pid", pid
    metric = rm.scope_metrics.add().metrics.add()
    metric.name = "workhorse.node.active"
    point = metric.gauge.data_points.add()
    point.as_double = 1.0
    point.time_unix_nano = int(2000 * 1e9)
    attributes = (("node", node), ("wf.activity", activity)) if activity else (("node", node),)
    for key, val in attributes:
        a = point.attributes.add()
        a.key, a.value.string_value = key, val
    return req.SerializeToString()
