---
type: format
slug: otlp-metric-point-record
title: OTLP metric point record
---
# OTLP metric point record

The decoded intermediate representation of one OpenTelemetry metric data point, produced by [parse_metrics](./concepts/groom-otlp-module.md#parse_metrics) and consumed by the store and alert ingestion. Metric points of gauge and sum kinds are extracted; other kinds (histogram, exponential histogram, summary) are skipped. Resource identity (run_id, workflow, repo, branch, run_dir, workspace, pid) is denormalized from the OTLP resource, because metrics reach groom early (heartbeats and node.active start at second zero) while spans export only when a node completes, so the native run's dashboard row is materialized from metrics and needs the same identity a span carries.

- code: groom/groom/otlp.py::parse_metrics
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
- semantics: run's artifact directory path, denormalized from the OTLP resource

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

### field-name

- type: `str`
- default: `""`
- required: true
- semantics: OpenTelemetry metric name

### field-ts

- type: `float`
- required: true
- semantics: metric point timestamp as a Unix timestamp (seconds since epoch), converted from nanoseconds

### field-value

- type: `float`
- required: true
- semantics: metric value, extracted as either `as_double` or `as_int` and coerced to float

### field-attrs

- type: `dict[str, Any]`
- default: `{}`
- required: true
- semantics: flattened metric point attributes from the protobuf (JSON-encoded for storage and querying)

