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
- first-party public members: the groom-owned model surface is exactly `LIVENESS_METRICS`, `WorkflowState`, `GateInfo`, `WorkflowContainer`, `AnswerResult`, and `RunTelemetry`.
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
- detail: [run telemetry](run-telemetry.md)
- meaning: the complete shared vocabulary of metrics that prove a workhorse process is alive; alert ingestion updates the telemetry hot cache from them and durable metric storage excludes them.

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
