---
type: format
slug: otlp-span-record
title: OTLP span record
---
# OTLP span record

The decoded intermediate representation of one OpenTelemetry span, produced by [parse_traces](./concepts/groom-otlp-module.md#parse_traces) and consumed by the store and alert ingestion. The span identity (trace_id, span_id, parent_id) comes directly from the protobuf; resource identity (run_id, workflow, repo, branch) is denormalized from the OTLP resource attributes so the store and alerts never need to re-join resources. Span attributes, events, and status message are flattened into the `attrs` dict, which the store JSON-encodes for later querying.

- code: groom/groom/otlp.py::parse_traces
- tests: groom/tests/test_telemetry.py

## Fields

### field-trace-id

- type: `str`
- required: true
- semantics: OpenTelemetry trace identifier, hex-encoded

### field-span-id

- type: `str`
- required: true
- semantics: OpenTelemetry span identifier, hex-encoded

### field-parent-id

- type: `str`
- default: `""`
- required: true
- semantics: OpenTelemetry parent span identifier, hex-encoded (empty for root spans)

### field-run-id

- type: `str`
- required: true
- semantics: workhorse run identifier, denormalized from the OTLP resource

### field-workflow

- type: `str`
- default: `""`
- required: true
- semantics: workflow name, denormalized from the OTLP resource

### field-repo

- type: `str`
- default: `""`
- required: true
- semantics: repository identity, denormalized from the OTLP resource

### field-branch

- type: `str`
- default: `""`
- required: true
- semantics: repository branch, denormalized from the OTLP resource

### field-run-dir

- type: `str`
- default: `""`
- required: true
- semantics: run's artifact directory path, denormalized from the OTLP resource for span → prompt.md / output.json lookup

### field-workspace

- type: `str`
- default: `""`
- required: true
- semantics: workspace (repository working tree) path for same-host native runs, denormalized from the OTLP resource (empty for containerized producers)

### field-pid

- type: `int | None`
- default: `None`
- required: false
- semantics: process identifier of the native producer, denormalized from the OTLP resource

### field-resume-generation

- type: `int | None`
- default: `None`
- required: false
- semantics: how many times this run dir has been started (resume count), denormalized from the OTLP resource (separates crash-and-resume gaps from idle periods)

### field-node

- type: `str`
- default: `""`
- required: true
- semantics: workhorse node name from the span attributes (prefer `workhorse.node`), falling back to the span name

### field-name

- type: `str`
- default: `""`
- required: true
- semantics: OpenTelemetry span name

### field-start-ts

- type: `float`
- required: true
- semantics: span start time as a Unix timestamp (seconds since epoch), converted from nanoseconds

### field-end-ts

- type: `float`
- required: true
- semantics: span end time as a Unix timestamp (seconds since epoch), converted from nanoseconds

### field-status

- type: `str`
- default: `"UNSET"`
- required: true
- semantics: span status as a normalized name — `"UNSET"`, `"OK"`, or `"ERROR"` — derived from the protobuf status code

### field-attrs

- type: `dict[str, Any]`
- default: `{}`
- required: true
- semantics: flattened span attributes from the protobuf, including nested events and status message (JSON-encoded for storage and querying)
- nested:
  - events: array of event objects, each with `name`, `ts` (Unix timestamp), and `attrs` (event attributes)
  - status_message: the span's status message, present only when non-empty

