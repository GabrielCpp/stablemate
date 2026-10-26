---
type: concept
title: Telemetry and logs
---
# Telemetry and logs

A run meant to go on for days is a run nobody watches. Workhorse streams OpenTelemetry spans,
metrics and log records to a local collector, so something else can tell a long cap wait from a
hang. Telemetry is off unless a collector is there, and then it does nothing at all.

`WORKHORSE_OTEL` decides whether telemetry is on:

- Unset means auto. The run probes `OTEL_EXPORTER_OTLP_ENDPOINT`, default
  `http://127.0.0.1:8787`, with one TCP connect bounded by `WORKHORSE_OTEL_PROBE_S`, default 0.25
  seconds. Telemetry turns on only when the probe connects and the process is not a test run.
- `1`, `true` or `yes` forces it on, with no probe.
- `0`, `false` or `no` forces it off.

A run emits one root span, one span per node visit, and one span per agent turn with its
duration, tokens and cost. The turn span also names the node visit it belongs to, under the
same slug its live transcript file carries. The [agent turns](agent-turns.md) ladder adds span events for retry,
reframe, compact and watchdog kills. A backend that reports no cost leaves the cost attribute
absent rather than zero. A node's output adds to its own node-visit span too: each top-level
scalar becomes a `workhorse.out.<key>` attribute, a list becomes `workhorse.out.<key>.len`, and a
string over 128 characters or an output past the 32nd key is left off. Exports are best effort,
and `events.jsonl` in the [run directory](run-directory.md) stays the durable record.

Live gauges show where a run is while it is still going. A run heartbeat ticks every
`WORKHORSE_OTEL_HEARTBEAT_S` seconds, default 10, from a thread that keeps beating through a long
node or cap sleep. A turn's idle seconds stay small while the agent streams and climb while it is
wedged. Metrics export every `WORKHORSE_OTEL_METRIC_EXPORT_S` seconds, which defaults to the
heartbeat.

Logs go to stderr as `[<logger>] <message>`, at the level `WORKHORSE_LOG_LEVEL` names, default
`INFO`. While telemetry is on, the same records also go to the collector, stamped with the node
the run is in. A workflow can add its own span dimensions by overriding `labels()`.

- code: `workhorse/workhorse/otel.py::Telemetry` @c3d8848371ee
- code: `workhorse/workhorse/otel.py::OtelSettings` @c3d8848371ee
- code: `workhorse/workhorse/logsetup.py::setup` @dbe8304930de
- code: `workhorse/docs/TELEMETRY.md` @1a5a741770e1
