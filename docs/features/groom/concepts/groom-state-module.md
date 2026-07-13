---
type: concept
slug: groom-state-module
title: Groom state module
---
# Groom state module

The Groom state module is groom's process-local mutable-state boundary: it owns the in-memory [workflow registry](workflow-registry.md), [answer event log](answer-event-log.md), [dashboard client queue set](dashboard-client-queue-set.md), [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md), [per-gate answer lock](per-gate-answer-lock.md) registry, and [workflow gate clearer](workflow-gate-clearer.md) operations used by the [groom server](../http/groom.md). It imports the [workflow container](workflow-container.md) model and exposes only in-memory helpers; route handlers, websocket handlers, discovery, renderers, Docker helpers, sidecar sessions, and gate-answering code own all external I/O and call these helpers to mutate or observe shared process state.

- code: groom/groom/state.py
- refs: [workflow registry](workflow-registry.md), [answer event log](answer-event-log.md), [dashboard client queue set](dashboard-client-queue-set.md), [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md), [per-gate answer lock](per-gate-answer-lock.md), [workflow gate clearer](workflow-gate-clearer.md), [workflow container](workflow-container.md)
- verify: groom/tests/test_state.py::test_prune_drops_absent_keeps_present
- verify: groom/tests/test_state.py::test_prune_empty_present_removes_everything
- verify: groom/tests/test_state.py::test_prune_also_forgets_gate_locks_of_removed
- verify: groom/tests/test_state.py::test_prune_is_noop_when_all_present

## Contract

- purpose: provide the complete first-party module for groom state that is shared across the single running web process.
- import behavior: importing the module allocates empty in-memory containers for workflows, answer logs, dashboard clients, and gate locks, sets discovery scanning to true, and binds helper functions; it does not inspect Docker, read or write files, open sockets, render HTML, create background tasks, or start the web server.
- public data members: the public mutable containers are exactly `WORKFLOWS`, `LOG`, `CLIENTS`, and `SCANNING`.
- public function members: the public helper functions are exactly `gate_lock`, `upsert_workflow`, `clear_gate`, `prune_workflows`, `record_log`, `add_client`, `remove_client`, and `broadcast`.
- private storage: `_gate_locks` is private module state but part of the documented per-gate lock contract because public `gate_lock` creates entries and public `prune_workflows` deletes entries for vanished workflows.
- process scope: every value in this module is local to one Python process and one event loop; no Redis, database, broker, filesystem persistence, cross-process lock, or framework `app.state` participates.
- mutation boundary: callers own validation, normalization, I/O, rendering, websocket acceptance/sending, sidecar communication, and durable gate-file writes before or after calling these helpers.
- concurrency boundary: same-gate answer serialization is available only to callers that acquire a returned [per-gate answer lock](per-gate-answer-lock.md); other containers are plain in-memory objects without module-level locking.
- ownership: the more specific member concepts own detailed field semantics, effects, failure behavior, and consumer paths; this module owns the folded public-member inventory and import-time state contract.

## Fields

### field-workflows

- type: `dict[str, WorkflowContainer]`
- default: empty dictionary at module import
- required: true
- code: groom/groom/state.py::WORKFLOWS
- detail: [workflow registry](workflow-registry.md)
- meaning: process-local workflow storage keyed by workflow container id.

### field-log

- type: `collections.deque[dict]`
- default: empty deque with `maxlen=200` at module import
- required: true
- code: groom/groom/state.py::LOG
- detail: [answer event log](answer-event-log.md)
- meaning: bounded process-local history for completed dashboard answer attempts.

### field-clients

- type: `set[asyncio.Queue]`
- default: empty set at module import
- required: true
- code: groom/groom/state.py::CLIENTS
- detail: [dashboard client queue set](dashboard-client-queue-set.md)
- meaning: registered outbound queues for accepted browser dashboard websocket sessions.

### field-scanning

- type: `bool`
- default: `True` at module import
- required: true
- code: groom/groom/state.py::SCANNING
- detail: [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md)
- meaning: process-local flag indicating that startup or manual container discovery is still in flight, so the dashboard renders loading state instead of a final empty state.

### field-gate-locks

- type: `dict[str, asyncio.Lock]`
- default: empty dictionary at module import
- required: true
- code: groom/groom/state.py::_gate_locks
- detail: [per-gate answer lock](per-gate-answer-lock.md)
- meaning: private lock registry keyed by the exact `container_id::file_path` pair used for same-gate answer serialization.

## Public Members

### method-gate-lock

- sig: `gate_lock(container_id: str, file_path: str) -> asyncio.Lock`
- abstract: false
- raises: ordinary lock-allocation or mapping errors propagate; no domain-specific error is returned.
- code: groom/groom/state.py::gate_lock
- detail: [per-gate answer lock](per-gate-answer-lock.md#method-gate-lock)

Returns the shared same-gate answer lock for one workflow container id and gate file path pair, creating an unlocked lock when the pair has not been seen in this process.

### method-upsert-workflow

- sig: `upsert_workflow(container_id: str, **fields: object) -> WorkflowContainer`
- abstract: false
- raises: ordinary dataclass construction or attribute-assignment errors propagate; no domain-specific error is returned.
- code: groom/groom/state.py::upsert_workflow
- detail: [workflow registry](workflow-registry.md#method-upsert-workflow)
- create default: when the workflow id is not already present and no non-empty `name` field is supplied, the new [workflow container](workflow-container.md) uses the first twelve characters of `container_id` as its display name.
- update rule: only supplied fields whose value is not `None` and whose name already exists on the stored [workflow container](workflow-container.md) are assigned; omitted fields, explicit `None` values, and unknown field names leave the stored container unchanged.

Creates or partially updates one workflow registry entry and returns the stored mutable [workflow container](workflow-container.md), preserving omitted, `None`, and unknown fields.

### method-clear-gate

- sig: `clear_gate(container_id: str, file_path: str) -> None`
- abstract: false
- raises: ordinary workflow or gate-map mutation errors propagate; no domain-specific error is returned.
- detail: [workflow gate clearer](workflow-gate-clearer.md#method-clear-gate)

Removes one gate entry from an existing workflow container's gate map when both the workflow and gate key exist, treating missing workflows and missing gates as no-ops.

### method-prune-workflows

- sig: `prune_workflows(present_ids: set[str]) -> list[str]`
- abstract: false
- raises: ordinary mapping mutation errors propagate; no domain-specific error is returned.
- code: groom/groom/state.py::prune_workflows
- verify: groom/tests/test_state.py::test_prune_drops_absent_keeps_present
- verify: groom/tests/test_state.py::test_prune_empty_present_removes_everything
- verify: groom/tests/test_state.py::test_prune_also_forgets_gate_locks_of_removed
- verify: groom/tests/test_state.py::test_prune_is_noop_when_all_present
- detail: [workflow registry](workflow-registry.md#method-prune-workflows)

Deletes workflow registry entries whose ids are absent from the supplied present-id set and forgets every private gate lock scoped to each removed workflow.

### method-record-log

- sig: `record_log(event: dict) -> None`
- abstract: false
- raises: ordinary deque append errors propagate; no domain-specific error is returned.
- code: groom/groom/state.py::record_log
- detail: [answer event log](answer-event-log.md#method-record-answer-log-entry)

Appends one caller-built answer event dictionary to the bounded in-memory answer event log without validation, normalization, cloning, broadcasting, or persistence.

### method-add-client

- sig: `add_client(queue: asyncio.Queue) -> None`
- abstract: false
- raises: ordinary set membership errors propagate; no domain-specific error is returned.
- code: groom/groom/state.py::add_client
- detail: [dashboard client queue set](dashboard-client-queue-set.md#method-register-dashboard-client)

Registers one dashboard websocket outbound queue in the process-local client set for future fragment broadcasts.

### method-remove-client

- sig: `remove_client(queue: asyncio.Queue) -> None`
- abstract: false
- raises: ordinary set discard errors propagate; no domain-specific error is returned.
- code: groom/groom/state.py::remove_client
- detail: [dashboard client queue set](dashboard-client-queue-set.md#method-unregister-dashboard-client)

Unregisters one dashboard websocket outbound queue from future fragment broadcasts, tolerating an absent queue.

### method-broadcast

- sig: `async broadcast(html_fragment: str) -> None`
- abstract: false
- raises: propagates cancellation or the first exception raised by a target queue's awaitable `put` operation.
- code: groom/groom/state.py::broadcast
- detail: [dashboard client queue set](dashboard-client-queue-set.md#method-broadcast-dashboard-fragment)

Enqueues one already-rendered HTML fragment to every dashboard client queue present in a snapshot of the client set at the start of the broadcast pass.

## Algorithms

### algorithm-module-initialization

- step: Importing the module imports standard-library async and bounded-sequence helpers and the first-party [workflow container](workflow-container.md) model type.
- step: The module creates an empty workflow registry, empty bounded answer log, empty dashboard client set, true scanning flag, and empty private gate-lock registry.
- step: The module exposes helper functions that mutate only those in-memory objects and the workflow containers stored inside them.
- step: The import completes without starting discovery, accepting clients, loading templates, inspecting containers, reading gate files, or broadcasting dashboard fragments.

### algorithm-state-helper-boundaries

- step: External callers decide which workflow id, gate path, queue object, log event, or HTML fragment should be passed to the state module.
- step: The state module performs only the local lookup, insertion, deletion, append, or queue-put operation documented by the selected helper.
- step: The state module returns the stored workflow, removed id list, lock object, or `None` according to the helper contract.
- step: External callers retain responsibility for rendering, persistence, Docker and sidecar I/O, websocket frame transmission, user-visible errors, and any post-mutation broadcasts.

## Non-Responsibilities

- no persistence: does not write workflow state, answer logs, client membership, scanning state, or locks to disk or an external service.
- no discovery: does not inspect Docker, start scans, decide whether pruning is safe during Docker outages, or update `SCANNING` by itself.
- no rendering: does not produce dashboard shell fragments, notification scripts, status counts, row HTML, or websocket protocol frames.
- no validation: does not normalize container ids, validate gate paths, validate answer event schemas, validate queue ownership, or coerce workflow-container field values.
- no transport ownership: does not accept websocket connections, close sockets, run send loops, contact sidecars, or retry failed client queues.
