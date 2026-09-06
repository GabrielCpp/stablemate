---
type: concept
slug: telemetry-instrumentation
title: OpenTelemetry instrumentation
---
# OpenTelemetry instrumentation

The telemetry facade observes one workhorse run when its collector gate enables it. With
`WORKHORSE_OTEL=1` it builds telemetry without probing; with `WORKHORSE_OTEL=0`, or when the
unset auto mode cannot reach `OTEL_EXPORTER_OTLP_ENDPOINT`, it uses an inert adapter. Auto mode
also stays off in test processes. Every public facade call is fail-soft: telemetry failures are
discarded rather than changing workflow execution.

The active adapter exports a root run span, nested state and node-visit spans, agent-turn spans,
wait spans and recovery events. It records normalized duration, token and cost attributes,
workflow labels, repository snapshots, resume generation, terminal outcome and error
classification. Periodic metrics expose gas, refuels, node/wait/turn activity and elapsed time,
plus run, turn and cap-wait heartbeats. Logging is attached only after a provider is built and is
detached before provider shutdown.

- code: `workhorse/workhorse/otel.py::Telemetry`
- code: `workhorse/workhorse/otel.py::TelemetryHost`
- code: `workhorse/workhorse/otel.py::OtelSettings`
- code: `workhorse/workhorse/otel.py::install`
- code: `workhorse/workhorse/otel.py::start_run`
- code: `workhorse/workhorse/otel.py::end_run`
- code: `workhorse/workhorse/otel.py::record_event`
- code: `workhorse/workhorse/otel.py::state_start`
- code: `workhorse/workhorse/otel.py::state_end`
- code: `workhorse/workhorse/otel.py::scope`
- code: `workhorse/workhorse/otel.py::wait`
- code: `workhorse/workhorse/otel.py::turn_start`
- code: `workhorse/workhorse/otel.py::turn_end`
- code: `workhorse/workhorse/otel.py::turn_result`
- code: `workhorse/workhorse/otel.py::turn_event`
- code: `workhorse/workhorse/otel.py::heartbeat`
- code: `workhorse/workhorse/otel.py::turn_heartbeat`
- code: `workhorse/workhorse/otel.py::current_node`
- code: `workhorse/workhorse/otel.py::current_repository`
- code: `workhorse/workhorse/otel.py::set_labels`
- code: `workhorse/workhorse/otel.py::turn_session`
- tests: `workhorse/tests/test_otel.py`

## Fields

### forced
- type: `bool | None`
- default: `None` — auto mode uses the collector probe
- verify: json_path(path="OtelSettings.forced", equals=null)
- required: false
- verify: json_path(path="OtelSettings.forced.required", equals=false)
- semantics: `true` forces telemetry on and `false` forces it off
- verify: json_path(path="OtelSettings.forced.semantics", equals="true forces telemetry on and false forces it off")
- code: `workhorse/workhorse/otel.py::OtelSettings`

### endpoint
- type: `str`
- default: `http://127.0.0.1:8787`
- verify: json_path(path="OtelSettings.endpoint", equals="http://127.0.0.1:8787")
- required: false
- verify: json_path(path="OtelSettings.endpoint.required", equals=false)
- semantics: OTLP HTTP collector endpoint with trailing slash removed
- verify: json_path(path="OtelSettings.endpoint.semantics", equals="OTLP HTTP collector endpoint with trailing slash removed")
- code: `workhorse/workhorse/otel.py::OtelSettings`

### probe_timeout_s
- type: `float`
- default: `0.25`
- verify: json_path(path="OtelSettings.probe_timeout_s", equals=0.25)
- required: false
- verify: json_path(path="OtelSettings.probe_timeout_s.required", equals=false)
- semantics: maximum seconds for the auto-mode TCP reachability probe
- verify: json_path(path="OtelSettings.probe_timeout_s.semantics", equals="maximum seconds for the auto-mode TCP reachability probe")
- code: `workhorse/workhorse/otel.py::OtelSettings`

### heartbeat_every_s
- type: `float`
- default: `10.0`
- verify: json_path(path="OtelSettings.heartbeat_every_s", equals=10.0)
- required: false
- verify: json_path(path="OtelSettings.heartbeat_every_s.required", equals=false)
- semantics: interval for process and turn liveness ticks
- verify: json_path(path="OtelSettings.heartbeat_every_s.semantics", equals="interval for process and turn liveness ticks")
- code: `workhorse/workhorse/otel.py::OtelSettings`

### metric_export_every_s
- type: `float`
- default: `10.0`
- required: false
- semantics: an explicit workhorse seconds setting takes precedence over the SDK millisecond setting
- verify: json_path(path="OtelSettings.metric_export_every_s", equals=3.0)
- semantics: the SDK millisecond setting takes precedence over the heartbeat interval when the workhorse seconds setting is absent
- verify: json_path(path="OtelSettings.metric_export_every_s", equals=15.0)
- semantics: the heartbeat interval supplies the metric export interval when neither override is valid
- verify: json_path(path="OtelSettings.metric_export_every_s", equals=10.0)
- code: `workhorse/workhorse/otel.py::OtelSettings`

## Methods

### from_env
- sig: `OtelSettings.from_env(environ: Mapping[str, str]) -> OtelSettings`
- does: reads telemetry environment values once and returns an immutable settings value
- verify: json_path(path="OtelSettings.endpoint", equals="http://collector:4318")
- raises: `ValueError` when a seconds-valued setting is malformed
- returns: settings with defaults, normalized endpoint, tri-state enablement, heartbeat interval, and metric export interval
- verify: json_path(path="OtelSettings.forced", equals=true)
- code: `workhorse/workhorse/otel.py::OtelSettings.from_env`
- tests: `workhorse/tests/test_otel.py::test_settings_are_read_from_the_mapping_it_is_handed`

### start_run
- sig: `TelemetryHost.start_run(workflow: str, run_id: str, run_dir: str | None = None) -> None`
- does: selects the null adapter when forced off, running in a test process, or the collector is unreachable in auto mode
- verify: unchanged(subject="the inactive telemetry host")
- does: builds the active adapter and opens the run root span when telemetry is enabled
- verify: emitted(event="run root span", count=1)
- does: leaves an already-enabled host unchanged when called again
- verify: unchanged(subject="the already-enabled telemetry host")
- raises: no exception to the workflow when probing or telemetry construction fails
- returns: `None`
- code: `workhorse/workhorse/otel.py::TelemetryHost.start_run`
- tests: `workhorse/tests/test_otel.py::test_auto_activates_when_the_collector_answers`, `workhorse/tests/test_otel.py::test_force_on_skips_the_probe`

### end_run
- sig: `TelemetryHost.end_run(status: str, error: str | None = None, error_class: str = "", error_kind: str = "") -> None`
- does: stops heartbeats
- verify: emitted(event="run heartbeat after finalization", count=0)
- does: closes open waits
- verify: emitted(event="interrupted wait closure", count=1)
- does: closes open spans
- verify: emitted(event="abandoned span closure", count=1)
- does: records the terminal status
- verify: json_path(path="$.workhorse.terminal", equals="terminal")
- does: records error metadata
- verify: json_path(path="$.error.class", equals="RuntimeError")
- does: detaches logging
- verify: absent(subject="OTel logging handler after finalization")
- does: flushes exporters
- verify: emitted(event="telemetry export", count=1)
- does: shuts down telemetry
- verify: emitted(event="telemetry shutdown", count=1)
- does: ignores repeated calls after the first finalization
- verify: unchanged(subject="the finalized telemetry host")
- returns: `None`
- code: `workhorse/workhorse/otel.py::TelemetryHost.end_run`
- tests: `workhorse/tests/test_otel.py::test_end_run_is_idempotent_and_the_first_status_wins`
