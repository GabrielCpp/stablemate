---
type: concept
slug: groom-models-module
title: Groom models module
---
# Groom models module

The Groom models module is the first-party in-memory data-shape boundary shared by the [groom server](../http/groom.md), discovery, rendering, gate answering, sidecar handling, telemetry ingestion, and alerting layers. It defines the process-local [workflow state](workflow-state.md), [gate info](gate-info.md), [workflow container](workflow-container.md), [answer result](../answer-result.md), and [run telemetry](run-telemetry.md) contracts, plus the shared liveness-metric vocabulary. It owns no Docker access, async transports, file I/O, rendering, persistence, locking, or state transitions; those behaviors live in the consuming modules that link back to these model nodes.

- code: groom/groom/models.py
- refs: [workflow state](workflow-state.md), [gate info](gate-info.md), [workflow container](workflow-container.md), [answer result](../answer-result.md), [run telemetry](run-telemetry.md)

## Contract

- purpose: provide the complete set of groom-owned plain model symbols that other groom modules exchange in memory.
- import behavior: importing the module binds the enum and dataclass types only; it performs no Docker subprocess calls, filesystem reads or writes, network calls, websocket registration, background task creation, logging, environment inspection, or workflow-registry mutation.
- first-party public members: the groom-owned model surface is exactly `LIVENESS_METRICS`, `UNARCHIVED_DELETABLE_METRICS`, `ARCHIVED_METRICS`, `WorkflowState`, `GateInfo`, `WorkflowContainer`, `AnswerResult`, and `RunTelemetry`.
- standard-library names: `dataclass`, `field`, and `Enum` are imported helper names from the Python standard library; they are not groom-owned domain concepts and do not get downstream OKF crawl items.
- validation boundary: the model classes do not validate, normalize, coerce, serialize, lock, persist, or broadcast their values; callers supply already-normalized values and own every side effect.
- mutability: dataclass instances are mutable process-local records; enum members are immutable string-valued lifecycle labels.
- persistence: groom-model — no model in this module persists itself to disk, a database, Docker metadata, or a websocket frame.
- verify: absent(subject="model persistence output outside process memory")
- persistence: groom-model — persistence or reconstruction happens through documented discovery, sidecar, gate-file, and push payload paths.
- verify: created(subject="model state reconstructed from a documented discovery, sidecar, gate-file, or push payload path")
- dependency boundary: the module depends only on standard-library dataclass and enum machinery and does not import other groom modules, preventing model import from starting application behavior.
- ownership: the more specific member nodes own field-level contracts, state-transition rules, producers, consumers, and verification anchors; this module owns the folded membership and side-effect-free import contract.

## Fields

### field-workflow-state

- type: [workflow state](workflow-state.md) enum class
- default: class object bound during module import
- required: true
- detail: [workflow state](workflow-state.md)
- meaning: lifecycle label type stored by workflow-container records and rendered throughout dashboard state projections.

### field-liveness-metrics

- type: `tuple[str, str, str]`
- default: `("workhorse.run.heartbeat", "workhorse.turn.heartbeat", "workhorse.cap_wait.heartbeat")`
- required: true
- semantics: the tuple is the complete shared vocabulary of metric names that prove a workhorse process is alive: run heartbeat, streaming-turn heartbeat, and cap-wait heartbeat.
- semantics: `groom.alerts.ingest_metrics` consumes every name in this tuple as process evidence and updates the hot-cache heartbeat timestamps.
- semantics: `groom.alerts.ingest_metrics` does not require the point to also land as a durable metric row before it updates the hot-cache heartbeat timestamp.
- semantics: `groom.store.insert_metrics` drops every point whose name is in this tuple before acquiring the writer lock.
- verify: absent(subject="a store-lock acquisition when a metric batch contains only liveness names")
- semantics: `groom.store.insert_metrics` writes no metric rows when a batch contains only names in this tuple.
- verify: absent(subject="current liveness heartbeat rows in the metrics table")
- code: groom/groom/models.py::LIVENESS_METRICS
- tests: groom/tests/test_telemetry.py::test_insert_metrics_never_stores_liveness_ticks
- tests: groom/tests/test_telemetry.py::test_the_never_archived_series_go_on_age_alone_with_no_archive_behind_them
- tests: groom/tests/test_archive.py::test_the_liveness_and_activity_gauges_never_reach_the_file
- tests: groom/tests/test_archive.py::test_prune_refuses_to_delete_a_run_no_archive_holds
- tests: groom/tests/test_store_contention.py::test_liveness_only_metric_batch_does_not_wait_for_the_store_lock
- detail: [run telemetry](run-telemetry.md)
- persistence: liveness-heartbeat-point — current liveness heartbeat points exist only in process memory.
- verify: absent(subject="current liveness heartbeat rows in the metrics table")
- persistence: liveness-heartbeat-point — points are not copied to SQLite or the telemetry archive.
- verify: absent(subject="liveness heartbeat records in telemetry.jsonl")
- persistence: diagnostic-activity-gauge — the seven gauges in `groom.models.UNARCHIVED_DELETABLE_METRICS` remain in SQLite for live queries but are never archived.
- verify: persists(subject="diagnostic activity gauge for a live run")
- persistence: liveness-heartbeat-point — legacy rows written before the ingest filter are deleted by age during `groom.store.prune`, without requiring an archived run id.
- verify: removed(subject="expired legacy liveness metric rows")
- persistence: budget-metric-row — rows still require archive authorization before `groom.store.prune` deletes them.
- verify: removed(subject="budget metric rows for a run with no archive recorded")

### field-archived-metrics

- type: `tuple[str, str, str, str]`
- default: `("workhorse.gas", "workhorse.gas.capacity", "workhorse.gas.refuels", "workhorse.cap_wait.remaining_s")`
- required: true
- semantics: the tuple is the complete vocabulary of metric names that are the run's budget-and-cap history — small, one point per event rather than per tick — and are the only metric names `groom.store` keeps past archival.
- semantics: `groom.store.archive_page` filters a run's `metric` page to only the names in this tuple before streaming it into the archive file.
- verify: persists(subject="a workhorse.gas metric row in the run's archived telemetry file")
- semantics: every other metric name is dropped from the archive.
- verify: omits(subject="the run's archived telemetry file", text="a metric row with a name not in the archived-metrics tuple")
- code: groom/groom/models.py::ARCHIVED_METRICS
- tests: groom/tests/test_archive.py::test_the_liveness_and_activity_gauges_never_reach_the_file
- detail: [run telemetry](run-telemetry.md)

### field-gate-info

- type: [gate info](gate-info.md) dataclass type
- default: class object bound during module import
- required: true
- detail: [gate info](gate-info.md)
- meaning: open operator-gate record type stored inside workflow-container gate maps.

### field-workflow-container

- type: [workflow container](workflow-container.md) dataclass type
- default: class object bound during module import
- required: true
- detail: [workflow container](workflow-container.md)
- meaning: mutable process-local workflow record type held by the registry and consumed by dashboard, discovery, push, sidecar, and answer paths.

### field-answer-result

- type: [answer result](../answer-result.md) dataclass type
- default: class object bound during module import
- required: true
- detail: [answer result](../answer-result.md)
- meaning: gate-answering return shape consumed by the dashboard websocket answer handler.

### field-run-telemetry

- type: [run telemetry](run-telemetry.md) dataclass type
- default: class object bound during module import
- required: true
- detail: [run telemetry](run-telemetry.md)
- meaning: mutable hot-cache record keyed by run id for alert-rule state, live dashboard data, and native-run projection.
