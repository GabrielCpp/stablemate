---
type: concept
slug: dashboard-discovery-scanning-flag
title: Dashboard discovery scanning flag
---
# Dashboard discovery scanning flag

Dashboard discovery scanning flag is groom's process-local boolean owned by the [groom state module](groom-state-module.md#field-scanning) that says whether a container discovery pass is currently in flight. It rides the wire as the `scanning` boolean on every [dashboard state payload](../dashboard-state-payload.md#field-scanning) — both the socket push and the [HTTP resync](../http/groom.md#get-dashboard-state) — and the browser decides the wording from it. [Startup background discovery scan](startup-background-discovery-scan.md) clears it when initial discovery exits, and the [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) invocation mutates it around manual reconciliation so connected tabs can show provisional loading state during a scan.

The flag exists because an empty fleet is two different facts. *Not scanned yet* and *scanned and genuinely empty* look identical in the run list, and only the server knows which one it is holding. Sending the boolean rather than the sentence keeps that judgement on the server and the wording in the browser, which is the same split every other field on the payload obeys.

- code: groom/groom/state.py::SCANNING
- verify: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes
- verify: groom/tests/test_app.py::test_background_scan_clears_scanning_on_error
- verify: groom/tests/test_projection.py::test_state_message_reports_whether_discovery_is_still_running
- verify: groom/tests/test_app.py::test_api_state_and_the_socket_push_the_same_payload

## Contract

- scope: one in-memory boolean per groom server process; it is shared by HTTP handlers, background discovery, and every state projection inside that process.
- ownership: the flag is the `SCANNING` public data member of the [groom state module](groom-state-module.md#field-scanning); this concept owns its presentation-state semantics while the module concept owns the complete public-member inventory.
- initial value: `True`, so the first served dashboard can display discovery loading until startup discovery has either completed or failed through the background scan path.
- true meaning: a startup or manual container-discovery pass is considered in flight for dashboard presentation purposes.
- false meaning: no discovery pass is currently advertised to the dashboard; an empty fleet is a finished, honest answer unless a caller sets the flag true again.
- empty-fleet effect: when the frame carries `scanning: true`, the fleet is empty, *and* the operator's filter box is empty, the [runs live region](../gui/screens/groom-dashboard.md#runs-live-region) reads `Discovering containers…` instead of `No workhorse runs — nothing is running.`. The server picks neither string; it sends the boolean.
- filtered-empty rule: a non-empty filter query ignores the flag and shows the ordinary empty-result text, because the operator is narrowing the currently known fleet rather than waiting for discovery. The filter is client-side, so this decision is the browser's alone.
- wire effect: the [dashboard state payload](../dashboard-state-payload.md#field-scanning) serializes the raw boolean as `scanning`, and both the socket push and the HTTP resync body carry it. A tab that recovers by polling therefore learns the same loading state a tab on a live socket sees, from the same field.
- startup completion effect: [startup background discovery scan](startup-background-discovery-scan.md) sets the flag false after its reconciliation attempt exits, including when reconciliation raises, then broadcasts one state payload carrying the cleared flag.
- manual refresh start effect: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the flag true and broadcasts one state payload before Docker reconciliation starts, so connected tabs can see the loading state before scan results arrive.
- manual refresh completion effect: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the flag false after the reconciliation attempt exits; a successful refresh then broadcasts a second state payload and returns `ok: true` with the discovered workflow count.
- concurrency: no cross-process coordination, database, external broker, lock, reference count, or per-scan token participates; overlapping refreshes share the same process-local flag, so any refresh completion can clear the advertised loading state for the process.
- lifetime: resets to the initial value on process start and is lost on process exit.
- non-goal: the flag is presentation state only; it does not prove Docker is reachable, does not serialize scans, does not indicate that the workflow registry is complete, and does not change workflow, gate, sidecar, or browser selection data by itself.

## Fields

### field-value

- type: `bool`
- default: `True`
- required: true
- code: groom/groom/state.py::SCANNING
- meaning: current process-level discovery-loading state consumed by the JSON projection and mutated by startup and manual discovery orchestration.
- producer: module initialization creates the value before the server starts accepting requests; startup background discovery and manual refresh later assign boolean values directly.
- consumer: the state projection reads the value on every payload it builds; the browser's fleet island then reads the serialized field only after client-side filtering leaves no matching rows.
- visibility: serialized as the `scanning` boolean on every state payload, so it is visible verbatim to any client of `GET /api/state` as well as to the dashboard.
- detail: [groom state module field](groom-state-module.md#field-scanning)

## State Changes

- startup: module initialization sets the flag to `True` before the background discovery task is scheduled.
- startup scan completion: [startup background discovery scan](startup-background-discovery-scan.md) sets the flag to `False` in its cleanup path after initial reconciliation exits and before its completion shell broadcast.
- startup scan failure: initial reconciliation exceptions do not strand the flag; the cleanup path still sets it to `False` before the exception leaves the background scan coroutine.
- manual refresh start: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the flag to `True` before Docker reconciliation starts and before the pre-scan dashboard shell broadcast.
- manual refresh completion: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) clears the flag in the reconciliation `finally` path, so success and reconciliation errors both remove the advertised loading state.
- failed pre-scan broadcast: if the pre-scan dashboard shell broadcast raises before reconciliation starts, the manual refresh path leaves the flag `True` because it never reaches the reconciliation `finally` path.
- failed post-scan broadcast: if the post-scan dashboard shell broadcast raises after successful reconciliation, the flag has already been cleared to `False`.
- non-effects: reading the flag from renderers does not mutate workflow containers, gate records, websocket queues, Docker state, sidecar state, answer logs, answer files, or gate files.

## Readers

- [state message](groom-projection-module.md#method-state-message): the only direct server-side reader. It copies the flag into the payload's `scanning` field and makes no wording decision from it.
- [dashboard state payload](../dashboard-state-payload.md#field-scanning): carries the boolean verbatim on the socket push and on the HTTP resync body alike.
- [serve dashboard state](../http/groom.md#serve-dashboard-state): returns the same projection, so a polling client sees the same flag as a socket client.
- [dashboard shell broadcaster](dashboard-shell-broadcaster.md): observes the flag through the projection on every broadcast — after startup discovery, manual refresh start and completion, sidecar updates, push updates, answer handling, and every live-clock tick.
- the browser's fleet island: the only reader that turns the boolean into words, and only when the fleet is empty and the filter box is too.

## Writers

- module initialization: assigns `True` as the process default.
- [startup background discovery scan](startup-background-discovery-scan.md): assigns `False` after startup reconciliation exits, regardless of success or reconciliation failure.
- [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet): assigns `True` before the pre-scan broadcast and assigns `False` in the reconciliation cleanup path.

## Failure And Overlap Semantics

- startup reconciliation failure: the flag is still set to `False` before the background scan coroutine propagates the reconciliation exception.
- startup completion broadcast failure: the flag has already been set to `False`; the failed broadcast does not restore loading state.
- refresh pre-scan broadcast failure: the flag has been set to `True`, reconciliation is not attempted, and the refresh invocation does not reach its cleanup path.
- refresh reconciliation failure: the flag is set to `False` in the cleanup path and the invocation propagates the reconciliation failure without sending the post-scan broadcast or success response.
- refresh post-scan broadcast failure: the flag remains `False` after reconciliation and cleanup; the invocation propagates the broadcast failure instead of returning the success response.
- overlapping refreshes: the boolean is not scoped to a specific scan; when multiple refresh invocations overlap, each start can set `True` and each cleanup can set `False` without checking whether another scan is still running.

## Source Touchpoints

- field: `groom/groom/state.py::SCANNING` stores the value and sets its import-time default to `True`.
- reader: `groom/groom/projection.py::state_message` is the only direct source reader; it serializes the flag as `scanning` on every payload it builds.
- HTTP reader: `groom/groom/app.py::api_state` reaches the reader through `projection.state_message` and returns the flag in the resync body without mutating it.
- websocket reader: `groom/groom/app.py::_broadcast_shell` reaches the same projection before enqueueing the payload.
- browser reader: `groom/groom/assets/dashboard.js::Fleet` is the only consumer that converts the boolean into visible text.
- startup writer: `groom/groom/app.py::_background_scan` clears the flag to `False` in its cleanup path.
- refresh writer: `groom/groom/app.py::refresh` sets the flag to `True` before its pre-scan broadcast and clears it to `False` in the reconciliation cleanup path.
- non-touchpoints: discovery scanning, Docker I/O, sidecar sessions, gate answering, workflow upsert/prune helpers, and static dashboard document serving do not read or assign the flag directly. The served HTML in particular carries no loading state at all — the shell mounts with the client's own `scanning: true` default until the first payload arrives.
