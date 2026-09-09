---
type: format
slug: otlp-log-record
title: OTLP log record
---
# OTLP log record

The decoded intermediate representation of one OpenTelemetry log record, produced by [parse_logs](./concepts/groom-otlp-module.md#parse_logs) and consumed by the store. Script node diagnostics land here now that workhorse runs scripts in-process: their log records ride the engine's own logger and arrive with the same run_id and run_dir resource identity as spans. The node is read from the record's attributes rather than the trace context, since workhorse never makes its node spans current (trace_id would be zeroes).

- code: groom/groom/otlp.py::parse_logs
- tests: groom/tests/test_telemetry.py

## Fields

### field-run-id

- type: `str`
- default: `""`
- required: true
- semantics: workhorse run identifier, denormalized from the OTLP resource

### field-workflow

- type: `str`
- default: `""`
- required: true
- semantics: workflow name, denormalized from the OTLP resource

### field-run-dir

- type: `str`
- default: `""`
- required: true
- semantics: run's artifact directory path, denormalized from the OTLP resource for log → transcript lookup

### field-node

- type: `str`
- default: `""`
- required: true
- semantics: workhorse node name, read from the record's attributes (`node` attribute) rather than the trace context

### field-logger

- type: `str`
- default: `""`
- required: true
- semantics: logger name, preferring the record's `logger.name` attribute over the instrumentation scope's name

### field-severity

- type: `str`
- default: `"INFO"`
- required: true
- semantics: log severity level normalized to stdlib logging names (`"TRACE"`, `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"FATAL"`), derived from `severity_number` in preference to `severity_text`

### field-body

- type: `str`
- default: `""`
- required: true
- semantics: the log message body, parsed from the protobuf `Any` value and coerced to string

### field-ts

- type: `float`
- required: true
- semantics: log timestamp as a Unix timestamp (seconds since epoch), converted from nanoseconds (falls back to observed_time_unix_nano when time_unix_nano is unset)

### field-trace-id

- type: `str`
- default: `""`
- required: true
- semantics: OpenTelemetry trace identifier from the log record, hex-encoded (may be zeroes or empty because workhorse doesn't make its node spans current)

### field-attrs

- type: `dict[str, Any]`
- default: `{}`
- required: true
- semantics: flattened log record attributes from the protobuf (JSON-encoded for storage and querying)

