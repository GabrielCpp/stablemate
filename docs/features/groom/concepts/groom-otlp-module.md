---
type: concept
slug: groom-otlp-module
title: Groom OTLP parsing module
---
# Groom OTLP parsing module

Decode standard OTLP/HTTP protobuf export requests into plain dicts, ready for storage and alerting. The module speaks the real OTLP wire format (OpenTelemetry protocol buffers) so the workhorse producer can point the stock OTel SDK exporter at groom — and symmetrically at Jaeger or Tempo — with zero code change. Only decoding lives here; storage is handled by the store module and alert rules by the alerts module.

Records carry the workhorse resource identity (run_id, workflow, repo, branch) denormalized onto every span, log, and metric point, so the store and alert rules never need to re-join resources. A record whose resource carries no `run_id` is dropped at the single door every row arrives through — the module counts these drops by signal and warns once per batch rather than once per record, so a misconfigured emitter's systematic failure is visible rather than silent.

- code: groom/groom/otlp.py
- tests: groom/tests/test_telemetry.py

## Public members

### dropped_no_run_id

Returns a snapshot of the cumulative drop counter at call time. The count is cumulative for the process lifetime and accessible to `groom archive status`.

- sig: `dropped_no_run_id() -> dict[str, int]`
- returns: a dict mapping signal name (`"traces"`, `"logs"`, `"metrics"`) to the count of records refused for carrying no `run_id`
- code: groom/groom/otlp.py::dropped_no_run_id

### parse_traces

Decodes an OpenTelemetry `ExportTraceServiceRequest` protobuf into a list of span records. Spans whose resource carries no `run_id` are dropped and counted in the cumulative drop counter. All non-dropped spans have resource identity (run_id, workflow, repo, branch, run_dir, workspace, pid, resume_generation) denormalized from the OTLP resource; span identifiers (trace_id, span_id, parent_id) are hex-encoded from binary; timing values are converted from nanoseconds to Unix seconds; span attributes, events, and status message are flattened into an `attrs` dict for JSON encoding. The `node` field prefers the `workhorse.node` attribute but falls back to the span name when absent.

- sig: `parse_traces(body: bytes) -> list[dict[str, Any]]`
- raises: undecodable input raises an exception; the HTTP receiver turns this into a 400 response
- returns: a list of [OTLP span record](../otlp-span-record.md) dicts
- code: groom/groom/otlp.py::parse_traces
- tests: groom/tests/test_telemetry.py

### parse_logs

Decodes an OpenTelemetry `ExportLogsServiceRequest` protobuf into a list of log records. Log records whose resource carries no `run_id` are dropped and counted in the cumulative drop counter. The node is read from the record's attributes rather than the trace context (which is zeroes since workhorse node spans are never made current). The severity level is normalized from the protobuf `severity_number` in preference to `severity_text` (the latter may carry non-standard labels like Python OTel's "WARN" for WARNING). The timestamp (converted from nanoseconds to Unix seconds) falls back to `observed_time_unix_nano` when `time_unix_nano` is unset, so records do not land at the epoch. Non-dropped records have resource identity denormalized and attributes flattened.

- sig: `parse_logs(body: bytes) -> list[dict[str, Any]]`
- raises: undecodable input raises an exception; the HTTP receiver turns this into a 400 response
- returns: a list of [OTLP log record](../otlp-log-record.md) dicts
- code: groom/groom/otlp.py::parse_logs
- tests: groom/tests/test_telemetry.py

### parse_metrics

Decodes an OpenTelemetry `ExportMetricsServiceRequest` protobuf into a list of metric point records. Only gauge and sum data points are extracted; histogram, exponential histogram, and summary kinds are skipped entirely. Metric points whose resource carries no `run_id` are dropped and counted in the cumulative drop counter. Non-dropped points have resource identity denormalized (critical because metrics arrive early—heartbeats and liveness ticks at second zero—while spans export only at node completion), timing converted from nanoseconds to Unix seconds, and point values extracted as either `as_double` or `as_int` then coerced to float. Point attributes are flattened into an `attrs` dict.

- sig: `parse_metrics(body: bytes) -> list[dict[str, Any]]`
- raises: undecodable input raises an exception; the HTTP receiver turns this into a 400 response
- returns: a list of [OTLP metric point record](../otlp-metric-point-record.md) dicts
- code: groom/groom/otlp.py::parse_metrics
- tests: groom/tests/test_telemetry.py

