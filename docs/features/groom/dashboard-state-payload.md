---
type: format
slug: dashboard-state-payload
title: Dashboard state payload
---
# Dashboard state payload

Dashboard state payload is the JSON object that carries the whole fleet to a [groom dashboard](gui/screens/groom-dashboard.md) tab. It is produced by the [groom projection module](concepts/groom-projection-module.md) and reaches the browser two ways: pushed over [websocket-dashboard](http/groom.md#websocket-dashboard) on every state change and on the live clock, and returned as the body of [get dashboard state](http/groom.md#get-dashboard-state) when a tab resyncs.

Those two paths deliver **the same bytes**. That is the load-bearing property of this format and the reason it is documented once rather than as a socket shape and an HTTP shape: the resync path only runs when the socket has already failed, which is precisely when nobody is watching it, so a payload that differed there would rot unobserved and be discovered by an operator mid-incident. One projection function builds it, one [dashboard client store](concepts/dashboard-client-store.md) entry point consumes it.

It replaced an HTML fragment pair that was swapped into the page out-of-band. Nothing in this format is markup, and no part of it is ever assigned to `innerHTML`.

- file: not an on-disk artifact; this is a transient JSON payload, delivered over the websocket or as an HTTP response body.
- code: groom/groom/projection.py::state_message
- refs: [groom projection module](concepts/groom-projection-module.md), [runs fleet view](runs-fleet-view.md), [dashboard client store](concepts/dashboard-client-store.md), [dashboard resync poller](concepts/dashboard-resync-poller.md), [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md)
- verify: groom/tests/test_projection.py::test_state_message_is_json_serializable
- verify: groom/tests/test_projection.py::test_state_message_reports_whether_discovery_is_still_running
- verify: groom/tests/test_projection.py::test_status_bar_counts_states
- verify: groom/tests/test_projection.py::test_query_filters_the_fleet
- verify: groom/tests/test_projection.py::test_fleet_rows_order_blocked_then_live_then_dead_then_finished

## Contract

- producer: [state message](concepts/groom-projection-module.md#method-state-message) builds the payload from a caller-supplied workflow snapshot, the telemetry hot cache, and an injectable clock.
- media: `application/json`. One object, not a document, not a fragment, not a list.
- delivery — push: sent as one websocket text frame, serialized by the [dashboard websocket send loop](concepts/dashboard-websocket-send-loop.md). The frame is the object itself; there is no envelope, request id, acknowledgement id, or version field around it — the `type` field is the discriminator.
- delivery — pull: returned verbatim as the body of `GET /api/state`, which exists for exactly this reason and documents itself as returning the same payload the websocket pushes.
- delivery — handshake: the first frame a newly accepted websocket receives is this payload, byte-identical to what `GET /api/state` would have returned at that moment, so a tab starts from a full snapshot rather than from whatever the next change happens to be.
- consumers: exactly one — the client's `applyState()`. Blocked-push broadcasts, answer broadcasts, sidecar state broadcasts, progress/exited broadcasts, refresh broadcasts, the live clock, and the resync poller all converge on it.
- wholeness: always the entire fleet, never a delta. Single-run deltas use the separate `run` message, which carries a row of the same shape so the client merges it without a second code path.
- query scope: a query narrows `runs` only. `status` always counts the full fleet, because a count narrowed by one tab's filter would misreport the fleet it claims to describe.
- ordering: `runs` arrives in display order — blocked, then alive, then presumed-dead, then finished, ties broken by name — so a tick does not reshuffle the list and the client does not re-sort on receipt.
- scanning: `scanning` reports the process-local [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md) so the client can show a discovery spinner rather than an empty state; a not-yet-scanned fleet must not read as finished-and-empty.
- JSON primitives only: every value is a `str`, `int`, `float`, `bool`, `null`, list, or object. No dataclass, enum, `datetime`, or set escapes into it.
- no markup: the payload contains data, including operator-supplied gate question text, which travels as text and is rendered as text. Nothing in it is escaped for HTML because nothing in it becomes HTML.
- no companions: notifications and answer confirmations are separate `notify` and `answered` messages, delivered as their own frames. This payload never embeds them.
- excluded content: the open run's detail, the repository menu, the files tree, file content, diff content, and telemetry are not part of this format. They are per-selection data with their own endpoints, and pushing them to every tab would send bandwidth proportional to tabs × runs for data almost every tab would discard.
- mutation: projecting this payload mutates nothing — not workflow containers, gates, repositories, answer logs, websocket clients, or the scanning flag.
- failure model: no embedded error channel. A projection exception propagates before any send or queueing step completes, and a tab that misses a payload recovers on the next tick or through the [dashboard resync poller](concepts/dashboard-resync-poller.md).

## Inputs

### field: workflows-input

- type: `list[WorkflowContainer]`
- default: none
- required: true
- consumer-use: projected into `runs` (filtered) and counted into `status` (unfiltered).
- mutation: not mutated.
- meaning: the caller-supplied fleet snapshot.

### field: query-input

- type: `str`
- default: `""`
- required: false
- consumer-use: passed to the fleet-row projection only.
- normalization: matching is case-insensitive over the run's identifying fields; the projection does not parse the query into terms.
- meaning: the run-list filter. It never changes `status` counts, repository totals, or worker totals.

### field: now-input

- type: `float | None`
- default: `None`, meaning wall-clock time
- required: false
- consumer-use: every time-derived label and duration in the payload is computed against it.
- meaning: the injectable clock, which is what lets a test pin liveness labels instead of asserting a range.

### field: discovery-scanning-flag-input

- type: `bool`
- default: process-local initial value is `True`
- required: true
- code: groom/groom/state.py::SCANNING
- consumer-use: read from module state rather than passed as an argument, and copied into the payload's `scanning` field.
- meaning: whether startup or manual discovery is still in flight.

## Fields

### field-type

- type: `str`
- default: `"state"`
- required: true
- meaning: the message discriminator the client dispatches on. Present on the HTTP body too, so the two paths really are the same bytes rather than the same bytes plus a wrapper.

### field-ts

- type: `float` (epoch seconds)
- default: the resolved clock
- required: true
- meaning: when the payload was projected. Every label in it was computed against this instant.

### field-scanning

- type: `bool`
- default: none
- required: true
- meaning: whether container discovery is still running, so an empty `runs` can be shown as a spinner rather than as inbox zero.

### field-runs

- type: `list` of run row objects
- default: `[]`
- required: true
- code: groom/groom/projection.py::fleet_rows
- detail: [runs fleet view](runs-fleet-view.md)
- ordering: blocked first, then alive, then presumed-dead, then finished; ties broken by name.
- filtering: narrowed by the query input when one is supplied.
- meaning: every run the tab should display, already ordered and already labelled.

### field-status

- type: `object` with `counts`, `repos`, `workers`
- default: none
- required: true
- code: groom/groom/projection.py::status_bar
- counts: one entry per workflow state — blocked, running, idle, finished — each an integer.
- repos: the number of distinct repository labels across the fleet; a workflow without a repository name contributes the fallback label.
- workers: the total number of workflows, regardless of state, gates, query, selection, or repository.
- meaning: the fleet-wide totals the status bar shows. Fleet-wide even while a query narrows the visible list.

## Algorithms

### algorithm-one-payload-two-paths

- step: A state change, the live clock, or a startup scan reaches the [dashboard shell broadcaster](concepts/dashboard-shell-broadcaster.md), which projects this payload once and broadcasts the same object to every tab.
- step: The [dashboard websocket send loop](concepts/dashboard-websocket-send-loop.md) serializes it per tab and sends one text frame.
- step: A tab whose socket has gone quiet instead calls `GET /api/state`, whose handler projects the same payload and returns it as the response body.
- step: Both land in `applyState()`, so the fleet a resynced tab shows and the fleet a pushed tab shows cannot differ.
