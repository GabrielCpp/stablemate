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

- code: groom/groom/models.py::RunTelemetry
- tests: groom/tests/test_telemetry.py::test_live_status_row_shape_is_the_cli_json_contract
- tests: groom/tests/test_telemetry.py::test_a_resumed_run_clears_the_previous_sessions_terminal
- tests: groom/tests/test_store_memory.py::test_terminated_run_evicted_after_grace

## Contract

- shape: mutable dataclass record with generated initialization, representation, and value equality over every field; it defines no custom methods, validation, serialization, locking, or persistence.
- identity: `run_id` is required and is the `RUNS` map key; a resumed workflow may reuse it, so newer producer timestamps clear terminal and alert state from an older session.
- lifecycle: alert ingestion creates a record on the first span or metric carrying a run id, progressively fills it from later evidence, and eviction removes terminal or long-silent entries from the process-local cache.
- time basis: ingest-time wall-clock timestamps govern absence checks, while producer timestamps preserve the newest reported beat and delimit the terminal session; no field is a durable event history.
- liveness: any [liveness metric](groom-models-module.md#field-liveness-metrics) updates heartbeat timestamps; the absence of such evidence is distinct from a slow node or active agent turn.
- terminal: a root span records `terminal` and `terminal_ts`; a later span or metric clears both and all fired alerts because it proves a resumed session under the same run id.
- alert state: `node_counts`, `node_labels`, and `fired` are mutable alert-engine working state; they are reset or retired by the alerting layer when forward progress, recovery, or resume disproves their associated conditions.
- persistence: the record is never written as a record to SQLite, a file, Docker, or a websocket frame; process restart starts with an empty cache and waits for new telemetry.

## Fields

### field-run-id

- type: `str`
- default: none
- required: true
- semantics: identifies the run and keys its hot-cache entry; OTLP ingest ignores spans and metrics with no run id.

### field-workflow

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty workflow name reported by telemetry for dashboard labels and alerts; empty means unknown.

### field-repo

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty repository identity reported by telemetry; empty means unknown.

### field-branch

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty repository branch reported by telemetry; empty means unknown.

### field-run-dir

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty run-directory path reported by telemetry; native-row materialization verifies whether it is readable on the host.

### field-workspace

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty workspace path reported by telemetry; native filesystem reads use it only after the run is recognized as local.

### field-pid

- type: `int | None`
- default: `None`
- required: false
- semantics: latest non-null producer process id; native-run liveness uses it as same-host evidence and `None` means unavailable.

### field-native

- type: `bool | None`
- default: `None`
- required: false
- semantics: cached verdict of whether `run_dir` exists on groom's host; `None` means the one-time locality check has not run.

### field-activity

- type: `str`
- default: `""`
- required: false
- semantics: latest non-empty live activity label from telemetry attributes, shown as a native workflow-row subtitle.

### field-backend

- type: `str`
- default: `""`
- required: false
- semantics: agent backend from the most recently completed `agent_turn` span; empty means no completed turn has reported one.

### field-model

- type: `str`
- default: `""`
- required: false
- semantics: model from the most recently completed `agent_turn` span; empty means no completed turn has reported one.

### field-first-seen-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: ingest wall-clock timestamp of the first observed span or metric; it bounds initial silence and eviction decisions.

### field-last-span-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: ingest wall-clock timestamp of the latest observed span; zero means no span has been ingested.

### field-last-heartbeat-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: groom wall-clock time of the latest liveness metric, used for stall and eviction windows without trusting producer clock skew.

### field-last-beat-ts

- type: `float`
- default: `0.0`
- required: false
- semantics: greatest producer-stamped timestamp among liveness metrics, exposed as the live-status row's last beat; zero means no liveness metric has arrived.

### field-current-node

- type: `str`
- default: `""`
- required: false
- semantics: current workhorse node from run heartbeat or node-active telemetry; empty means no open node is known.

### field-node-elapsed-s

- type: `float`
- default: `0.0`
- required: false
- semantics: latest elapsed seconds for the current node; it supports deterministic-work stuck detection and resets when that node closes.

### field-turn-idle-s

- type: `float`
- default: `0.0`
- required: false
- semantics: latest seconds since an active agent turn emitted output; it is reset when no turn remains active.

### field-turn-active

- type: `bool | None`
- default: `None`
- required: false
- semantics: whether telemetry reports an open agent turn; `None` distinguishes older producers that emit no turn-active gauge from a reported inactive turn.

### field-turn-elapsed-s

- type: `float`
- default: `0.0`
- required: false
- semantics: latest elapsed seconds for an active agent turn; it is reset when the turn becomes inactive.

### field-wait-kind

- type: `str`
- default: `""`
- required: false
- semantics: current explicit wait kind from telemetry, such as `operator`; empty means no current wait is known.

### field-wait-elapsed-s

- type: `float`
- default: `0.0`
- required: false
- semantics: latest elapsed seconds for the current explicit wait; it is reset when that wait closes.

### field-gas

- type: `float | None`
- default: `None`
- required: false
- semantics: latest workhorse gas gauge value; `None` means the producer has not emitted a gas reading.

### field-terminal

- type: `str`
- default: `""`
- required: false
- semantics: terminal status from the current session's root span; empty means no terminal has been observed or a newer signal resumed the run.

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
