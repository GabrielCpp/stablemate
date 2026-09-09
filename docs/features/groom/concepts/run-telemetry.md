---
type: concept
slug: run-telemetry
title: Run telemetry
---
# Run telemetry

Run telemetry is the mutable, process-local hot-cache record for one workhorse run, keyed by
`run_id` in the Groom state module's `RUNS` map. Telemetry alert ingestion
creates and updates it from decoded OTLP spans and metrics; the [groom projection module](groom-projection-module.md)
reads it to render liveness and run-detail data; the groom application uses it to materialize
same-host native workflow rows. It is not the durable telemetry store: spans, diagnostic metrics,
and logs belong to the SQLite store, while the three [liveness metrics](groom-models-module.md#field-liveness-metrics)
remain memory-only because they are needed only for the current live picture.
The [alert](alert.md) value is returned when an ingest or periodic rule newly pages an operator.

- code: groom/groom/models.py::RunTelemetry
- tests: groom/tests/test_telemetry.py::test_live_status_row_shape_is_the_cli_json_contract
- tests: groom/tests/test_telemetry.py::test_a_resumed_run_clears_the_previous_sessions_terminal
- tests: groom/tests/test_store_memory.py::test_terminated_run_evicted_after_grace
- detail: [alert](alert.md)

## Contract

- shape: mutable dataclass record with generated initialization, representation, and value equality over every field; it defines no custom methods, validation, serialization, locking, or persistence.
- identity: `run_id` is required and is the `RUNS` map key; a resumed workflow may reuse it, so newer producer timestamps clear terminal and alert state from an older session.
- lifecycle: alert ingestion creates a record on the first span or metric carrying a run id, progressively fills it from later evidence, and eviction removes terminal or long-silent entries from the process-local cache.
- time basis: ingest-time wall-clock timestamps govern absence checks, while producer timestamps preserve the newest reported beat and delimit the terminal session; no field is a durable event history.
- liveness: any [liveness metric](groom-models-module.md#field-liveness-metrics) updates heartbeat timestamps; the absence of such evidence is distinct from a slow node or active agent turn.
- terminal: a root span records `terminal` and `terminal_ts`; a later span or metric clears both and all fired alerts because it proves a resumed session under the same run id.
- alert state: `node_counts`, `node_labels`, and `fired` are mutable alert-engine working state; they are reset or retired by the alerting layer when forward progress, recovery, or resume disproves their associated conditions.
- persistence: run-telemetry — the record is never written to SQLite, a file, Docker, or a websocket frame
- persistence: run-telemetry — process restart starts with an empty cache and waits for new telemetry

## Methods

### stale_run_ids

- sig: `stale_run_ids(now: float | None = None) -> list[str]`
- does: returns terminal runs whose last evidence is older than the eviction grace window.
- does: returns non-terminal runs silent longer than the dead-run window.
- does: leaves all identified run ids in the cache without modification.
- verify: unchanged(subject="RUNS")
- returns: a list of run ids eligible for removal from the hot cache.
- verify: count(subject="stale run ids", equals=1)
- code: `groom/groom/alerts.py::stale_run_ids`
- tests: `groom/tests/test_store_memory.py::test_terminated_run_evicted_after_grace`

### note_native_ending

- sig: `note_native_ending(run: RunTelemetry, ending: str) -> list[Alert]`
- does: fires `DIED` when a native process disappears without a terminal record.
- does: fires `ENDED` for another native ending reported by the run record.
- returns: newly-fired alerts after per-run rule deduplication.
- verify: count(subject="native ending alerts", equals=1)
- code: `groom/groom/alerts.py::note_native_ending`
- tests: `groom/tests/test_native_row.py::test_a_vanished_pid_retires_a_run_that_never_recorded_an_ending`

### ingest_spans

- sig: `ingest_spans(spans: list[dict[str, Any]], now: float | None = None) -> list[Alert]`
- does: creates or updates one hot-cache record per span with run identity, location, activity, backend, model, timestamps, and terminal state.
- does: fires `ENDED` for a root `run:*` span and retires the run from absence-rule evaluation.
- does: fires `WATCHDOG` for a `watchdog_kill` event and `GAVE-UP` for a configured give-up node.
- does: counts completed node repeats only when the same workflow-label signature recurs.
- does: excludes cut spans and agent-turn retries from the repeat count.
- verify: absent(subject="cut spans in repeat count")
- does: fires `CHURN` at the configured repeat threshold.
- verify: emitted(event="CHURN", count=1)
- returns: newly-fired alerts, with duplicate `(run_id, rule)` pages omitted.
- verify: count(subject="span-ingest alerts", equals=2)
- code: `groom/groom/alerts.py::ingest_spans`
- tests: `groom/tests/test_telemetry.py::test_watchdog_and_giveup_fire_once_per_run`

### ingest_metrics

- sig: `ingest_metrics(points: list[dict[str, Any]], now: float | None = None) -> list[Alert]`
- does: creates or updates one hot-cache record per metric with liveness, node, turn, wait, activity, and gas state.
- does: treats each liveness metric as process evidence and stores its newest producer timestamp for live status.
- does: fires `BLOCKED` immediately when an operator wait opens and excludes cap and machine waits.
- does: retires `STUCK`, `BLOCKED`, and `WAITING` when the corresponding node or wait condition closes.
- verify: absent(subject="retired alert in fired set")
- does: resets churn on gas refuel.
- verify: unchanged(subject="node_counts")
- returns: newly-fired alerts after per-run rule deduplication.
- verify: count(subject="metric-ingest alerts", equals=1)
- code: `groom/groom/alerts.py::ingest_metrics`
- tests: `groom/tests/test_telemetry.py::test_an_operator_gate_pages_the_moment_it_opens`

### live_status

- sig: `live_status(run: str = "", now: float | None = None) -> list[dict[str, Any]]`
- does: projects each cached run with a producer heartbeat into the public live-status row shape.
- does: reports node, turn, wait, gas, last-beat, and alive values, with `alive` false after the live window.
- does: filters to the requested run id when `run` is non-empty and sorts rows newest heartbeat first.
- returns: JSON-compatible rows when the cache entry has a heartbeat
- verify: count(subject="live status rows", equals=1)
- returns: no rows when the cache entry lacks a heartbeat
- verify: count(subject="live status rows", equals=0)
- code: `groom/groom/alerts.py::live_status`
- tests: `groom/tests/test_telemetry.py::test_live_status_row_shape_is_the_cli_json_contract`

### live_run_ids

- sig: `live_run_ids(now: float | None = None) -> set[str]`
- does: returns exactly the run ids whose live-status rows are currently alive.
- returns: a set containing no id for a run whose latest heartbeat is outside the live window.
- verify: count(subject="currently live run ids", equals=1)
- code: `groom/groom/alerts.py::live_run_ids`
- tests: `groom/tests/test_telemetry.py::test_live_status_row_shape_is_the_cli_json_contract`

### check_time_rules

- sig: `check_time_rules(now: float | None = None) -> list[Alert]`
- does: fires `STALL` when a non-terminal run has emitted neither a span nor heartbeat beyond the stall threshold.
- does: fires `STUCK` when a heartbeating run has an active agent turn idle beyond the stuck threshold or deterministic work open beyond that threshold.
- does: excludes terminal runs from every rule with an early continue at the top of the per-run loop.
- does: excludes explicit waits from `STUCK` evaluation.
- does: evaluates `STALL` before the wait branch, so a run with an open wait still fires `STALL` once its silence crosses the stall threshold.
- does: fires `WAITING` when an unanswered operator wait exceeds the wait threshold while leaving cap and machine waits exempt.
- returns: newly-fired time-based alerts after per-run rule deduplication.
- verify: count(subject="time-rule alerts", equals=1)
- code: `groom/groom/alerts.py::check_time_rules`
- tests: `groom/tests/test_telemetry.py::test_stall_fires_on_silence_but_heartbeat_suppresses_it`

## Fields

### field-run-id

- type: `str`
- default: none
- required: true
- semantics: identifies the run and keys its hot-cache entry in the Groom state module's RUNS map
- verify: created(subject="cache entry for run_id")
- semantics: ingest ignores spans and metrics with no run id
- verify: absent(subject="cache entry from span without run id")

### field-workflow

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty workflow name reported by telemetry for dashboard labels and alerts
- semantics: empty means unknown.

### field-repo

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty repository identity reported by telemetry
- semantics: empty means unknown.

### field-branch

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty repository branch reported by telemetry.
- semantics: empty means unknown.

### field-run-dir

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty run-directory path reported by telemetry
- verify: created(subject="run_dir")
- semantics: native-row materialization uses it to determine if the run is on the same host as groom
- verify: persists(subject="run_dir")

### field-workspace

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty workspace path reported by telemetry
- verify: created(subject="workspace")
- semantics: native filesystem reads use it only after the run is recognized as local
- verify: persists(subject="workspace")

### field-pid

- type: `int | None`
- default: `None`
- required: false
- semantics: latest non-null process id from telemetry
- verify: json_path(path="pid", matches="^[0-9]+$")
- semantics: read by native-run liveness to decide whether the run's process is still alive on groom's host
- verify: emitted(event="DIED", count=1)
- semantics: `None` when the producer has not emitted a process id

### field-native

- type: `bool | None`
- default: `None`
- required: false
- semantics: cached verdict of whether `run_dir` exists on groom's host
- semantics: `None` means the one-time locality check has not run.

### field-activity

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty live activity label from telemetry attributes, shown as a native workflow-row subtitle.

### field-backend

- type: `str`
- default: `""`
- required: false
- semantics: agent backend from the most recently completed `agent_turn` span
- semantics: the field is empty when no completed `agent_turn` span has reported one

### field-model

- type: `str`
- default: `""`
- required: false
- semantics: model from the most recently completed `agent_turn` span
- semantics: the field is empty when no completed `agent_turn` span has reported one

### field-first-seen-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: ingest wall-clock timestamp recorded when the first span or metric for this run is observed
- verify: created(subject="first_seen_ts for newly-ingested run")
- semantics: included in stale-run and eviction calculations to determine whether a run has been idle beyond its grace window
- verify: removed(subject="run from cache after eviction grace period")

### field-last-span-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: ingest wall-clock timestamp of the latest observed span
- semantics: zero means no span has been ingested.

### field-last-heartbeat-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: groom wall-clock time of the latest liveness metric, used for stall and eviction windows without trusting producer clock skew.

### field-last-beat-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: greatest producer-stamped timestamp among liveness metrics, exposed as the live-status row's last beat
- semantics: zero when no liveness metric has arrived

### field-current-node

- type: `str`
- default: `""`
- required: false
- semantics: current workhorse node from run heartbeat or node-active telemetry.
- semantics: empty string indicates no open node is known.

### field-node-elapsed-s

- type: `float`
- default: `0.0`
- required: false
- semantics: latest elapsed seconds for the current node
- semantics: supports deterministic-work stuck detection
- semantics: resets when that node closes

### field-turn-idle-s

- type: `float`
- default: `0.0`
- required: false
- semantics: latest seconds since an active agent turn emitted output
- semantics: it is reset when no turn remains active

### field-turn-active

- type: `bool | None`
- default: `None`
- required: false
- semantics: whether telemetry reports an open agent turn
- verify: json_path(path="turn_active", equals=True)
- semantics: `None` distinguishes older producers that emit no turn-active gauge from a reported inactive turn
- verify: json_path(path="turn_active", absent=True)

### field-turn-elapsed-s

- type: `float`
- default: `0.0`
- required: false
- semantics: latest elapsed seconds for an active agent turn
- verify: json_path(path="turn_elapsed_s", matches="^[0-9]+(\\.[0-9]+)?$")
- semantics: zero when no agent turn remains active
- verify: json_path(path="turn_elapsed_s", equals=0.0)

### field-wait-kind

- type: `str`
- default: `""`
- required: false
- semantics: current explicit wait kind from telemetry, such as `operator`
- semantics: empty means no current wait is known.

### field-wait-elapsed-s

- type: `float`
- default: `0.0`
- required: false
- semantics: latest elapsed seconds for the current explicit wait
- verify: json_path(path="wait_elapsed_s", matches="^[0-9]+(\\.[0-9]+)?$")
- semantics: it is reset when that wait closes
- verify: json_path(path="wait_elapsed_s", equals=0.0)

### field-gas

- type: `float | None`
- default: `None`
- required: false
- semantics: latest workhorse gas gauge value
- semantics: `None` means the producer has not emitted a gas reading

### field-terminal

- type: `str`
- default: `""`
- required: false
- semantics: terminal status from the current session's root span
- verify: json_path(path="terminal", matches="^[a-z_]+$")
- semantics: empty when no terminal has been observed or a newer signal resumed the run
- verify: json_path(path="terminal", equals="")

### field-terminal-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: producer end timestamp paired with `terminal`, used to reject older evidence and clear stale terminal state only for newer evidence.

### field-node-counts

- type: `dict[str, int]`
- default: new empty dictionary per record
- required: false
- semantics: completed-node repeat counts for the current work item, used to trigger churn alerts and cleared by gas refuel or changed work labels.

### field-node-labels

- type: `dict[str, tuple[tuple[str, str], ...]]`
- default: new empty dictionary per record
- required: false
- semantics: last workflow-label signature per node, distinguishing repeated work from forward progress when evaluating churn.

### field-fired

- type: `set[str]`
- default: new empty set per record
- required: false
- semantics: alert-rule names already paged for this run, deduplicating pages until recovery, forward progress, wait closure, or a resumed session retires the applicable entries.
