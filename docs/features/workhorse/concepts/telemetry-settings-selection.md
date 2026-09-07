---
type: concept
slug: telemetry-settings-selection
title: Telemetry settings selection
---
# Telemetry settings selection

`OtelSettings.from_env` reads the telemetry environment once at run startup, so every
subsequent collector probe and exporter configuration uses one immutable, internally
consistent settings value. These fields are coordinated inputs rather than alternatives:
each applies to a separate part of the telemetry gate or export cadence.

Leave `forced` unset for normal operation: auto mode probes the configured `endpoint` for
at most `probe_timeout_s` before enabling telemetry. Set `forced` only to deliberately
override that decision. `heartbeat_every_s` determines the liveness tick cadence. The
metric export interval is selected in order from `WORKHORSE_OTEL_METRIC_EXPORT_S`, then
`OTEL_METRIC_EXPORT_INTERVAL` (converted from milliseconds), then the heartbeat interval;
invalid or non-positive explicit intervals fall through to the next source.

- code: `workhorse/workhorse/otel.py::OtelSettings`
- rule: leave `forced` unset for collector-probed auto mode; configure endpoint, probe timeout, heartbeat, and metric-export cadence according to the part of telemetry they control
- detail: [telemetry documentation scope](telemetry-documentation-scope.md)
