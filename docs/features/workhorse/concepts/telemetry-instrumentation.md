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
- code: `workhorse/workhorse/otel.py::CollectorProbe`
- code: `workhorse/workhorse/otel.py::TelemetryFactory`
- code: `workhorse/workhorse/otel.py::OtelSettings`
- code: `workhorse/workhorse/otel.py::set_repository_probe`
- code: `workhorse/workhorse/otel.py::set_head_probe`
- code: `workhorse/workhorse/otel.py::enabled`
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
- code: `workhorse/workhorse/otel.py::run_attribute`
- code: `workhorse/workhorse/otel.py::gas_level`
- code: `workhorse/workhorse/otel.py::gas_refuel`
- tests: `workhorse/tests/test_otel.py`
- detail: [telemetry documentation scope](telemetry-documentation-scope.md)

## Fields

### forced
- type: `bool | None`
- default: `None` — auto mode uses the collector probe
- verify: json_path(path="OtelSettings.forced", matches="^None$")
- required: false
- verify: json_path(path="OtelSettings.forced.required", equals=false)
- semantics: `true` forces telemetry on and `false` forces it off
- verify: json_path(path="OtelSettings.forced.semantics", equals="true forces telemetry on and false forces it off")
- code: `workhorse/workhorse/otel.py::OtelSettings`
- detail: [telemetry settings selection](telemetry-settings-selection.md)

### endpoint
- type: `str`
- default: `http://127.0.0.1:8787`
- verify: json_path(path="OtelSettings.endpoint", equals="http://127.0.0.1:8787")
- required: false
- verify: json_path(path="OtelSettings.endpoint.required", equals=false)
- semantics: OTLP HTTP collector endpoint with trailing slash removed
- verify: json_path(path="OtelSettings.endpoint.semantics", equals="OTLP HTTP collector endpoint with trailing slash removed")
- code: `workhorse/workhorse/otel.py::OtelSettings`
- detail: [telemetry settings selection](telemetry-settings-selection.md)

### probe_timeout_s
- type: `float`
- default: `0.25`
- verify: json_path(path="OtelSettings.probe_timeout_s", equals=0.25)
- required: false
- verify: json_path(path="OtelSettings.probe_timeout_s.required", equals=false)
- semantics: maximum seconds for the auto-mode TCP reachability probe
- verify: json_path(path="OtelSettings.probe_timeout_s.semantics", equals="maximum seconds for the auto-mode TCP reachability probe")
- code: `workhorse/workhorse/otel.py::OtelSettings`
- detail: [telemetry settings selection](telemetry-settings-selection.md)

### heartbeat_every_s
- type: `float`
- default: `10.0`
- verify: json_path(path="OtelSettings.heartbeat_every_s", equals=10.0)
- required: false
- verify: json_path(path="OtelSettings.heartbeat_every_s.required", equals=false)
- semantics: interval for process and turn liveness ticks
- verify: json_path(path="OtelSettings.heartbeat_every_s.semantics", equals="interval for process and turn liveness ticks")
- code: `workhorse/workhorse/otel.py::OtelSettings`
- detail: [telemetry settings selection](telemetry-settings-selection.md)

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
- detail: [telemetry settings selection](telemetry-settings-selection.md)

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

### set_repository_probe
- sig: `set_repository_probe(probe: RepositoryProbe | None) -> None`
- does: replaces the repository observation callback used for span boundary attributes
- verify: emitted(event="repository snapshot", count=1)
- does: restores the no-op observer when the argument is `None`
- verify: absent(subject="repository snapshot without an installed probe")
- returns: `None`
- code: `workhorse/workhorse/otel.py::set_repository_probe`
- tests: `workhorse/tests/test_gitstate.py::test_agent_node_and_turn_spans_use_their_own_multi_repo_scope`

### set_head_probe
- sig: `set_head_probe(probe: HeadProbe | None) -> None`
- does: adapts a single-HEAD callback into a repository observer that stamps a non-empty `git.head` value
- verify: json_path(path="git.head.start", matches=".+")
- does: clears repository observation when the argument is `None`
- verify: absent(subject="git.head.start after clearing the head probe")
- returns: `None`
- code: `workhorse/workhorse/otel.py::set_head_probe`
- tests: `workhorse/tests/test_gitstate.py::test_a_head_that_moves_inside_a_node_leaves_unequal_endpoints`

### enabled
- sig: `enabled() -> bool`
- does: reports `true` only when the installed host has an active exporting adapter
- verify: json_path(path="telemetry.enabled", equals=true)
- returns: `false` for the default null adapter
- verify: json_path(path="telemetry.enabled", equals=false)
- returns: `true` after an enabled run is built
- verify: json_path(path="telemetry.enabled", equals=true)
- code: `workhorse/workhorse/otel.py::enabled`
- tests: `workhorse/tests/test_otel.py::test_auto_activates_when_the_collector_answers`, `workhorse/tests/test_otel.py::test_noop_by_default_all_calls_inert`

### run_attribute
- sig: `run_attribute(name: str, value: str) -> None`
- does: writes the named string value onto the active run root span
- verify: json_path(path="workhorse.profile", equals="cheap")
- does: replaces an earlier value when the same name is written again before run completion
- verify: json_path(path="workhorse.profile", equals="local")
- does: drops a late write after the root span has ended without raising
- verify: unchanged(subject="the finalized run root span")
- returns: `None`
- code: `workhorse/workhorse/otel.py::run_attribute`
- tests: `workhorse/tests/test_otel.py::test_a_run_level_fact_lands_on_the_root_span_and_the_last_write_wins`

### gas_level
- sig: `gas_level(gas: int, capacity: int) -> None`
- does: sets the current remaining gas gauge to `gas`
- verify: json_path(path="workhorse.gas", equals=4999)
- does: sets the configured gas capacity gauge to `capacity`
- verify: json_path(path="workhorse.gas.capacity", equals=5000)
- returns: `None`
- code: `workhorse/workhorse/otel.py::gas_level`
- tests: `workhorse/tests/test_otel.py::test_gas_and_heartbeat_metrics_record`

### gas_refuel
- sig: `gas_refuel(node_id: str) -> None`
- does: increments the gas refuel counter once with the progress node as its `node` attribute
- verify: emitted(event="workhorse.gas.refuels", count=1)
- returns: `None`
- code: `workhorse/workhorse/otel.py::gas_refuel`
- tests: `workhorse/tests/test_otel.py::test_gas_and_heartbeat_metrics_record`
