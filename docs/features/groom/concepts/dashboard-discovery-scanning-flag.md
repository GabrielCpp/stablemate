---
type: concept
slug: dashboard-discovery-scanning-flag
title: Dashboard discovery scanning flag
---
# Dashboard discovery scanning flag

Dashboard discovery scanning flag is groom's process-local boolean owned by the [groom state module](groom-state-module.md#field-scanning) that tells dashboard renderers whether a container discovery pass is currently in flight. The [operator inbox](../operator-inbox.md) reads it when an empty inbox must choose between the normal inbox-zero state and the discovery-loading placeholder, the [dashboard shell fragment](../dashboard-shell-fragment.md#field-discovery-scanning-flag-input) carries that choice into websocket replacement HTML, the [search fragment endpoint](../http/groom.md#get-search-fragment) can return the same inbox loading placeholder for an empty unfiltered search response, [startup background discovery scan](startup-background-discovery-scan.md) clears it when initial discovery exits, and the [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) invocation mutates it around manual reconciliation so connected dashboard tabs can show provisional loading state during a scan.

- code: groom/groom/state.py::SCANNING
- verify: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes
- verify: groom/tests/test_app.py::test_background_scan_clears_scanning_on_error
- verify: groom/tests/test_render.py::test_empty_inbox_message
- verify: groom/tests/test_render.py::test_empty_inbox_shows_spinner_while_scanning
- verify: groom/tests/test_render.py::test_empty_inbox_shows_empty_state_when_not_scanning
- verify: groom/tests/test_render.py::test_search_with_query_shows_empty_not_spinner_even_while_scanning

## Contract

- scope: one in-memory boolean per groom server process; it is shared by HTTP handlers, background discovery, websocket shell rendering, and inbox rendering inside that process.
- ownership: the flag is the `SCANNING` public data member of the [groom state module](groom-state-module.md#field-scanning); this concept owns its presentation-state semantics while the module concept owns the complete public-member inventory.
- initial value: `True`, so the first served dashboard can display discovery loading until startup discovery has either completed or failed through the background scan path.
- true meaning: a startup or manual container-discovery pass is considered in flight for dashboard presentation purposes.
- false meaning: no discovery pass is currently advertised to the dashboard; an empty inbox should read as empty unless a caller sets the flag true before rendering.
- empty-inbox effect: when true and the inbox query is empty, the [operator inbox empty-or-loading method](../operator-inbox.md#method-render-empty-or-loading) renders `Discovering containers…` instead of `No incoming messages — inbox zero.`.
- filtered-empty rule: a non-empty inbox query ignores the flag and renders the ordinary empty-result text, because the operator is narrowing the current known fleet rather than waiting for discovery.
- shell-fragment effect: the [dashboard shell fragment](../dashboard-shell-fragment.md) does not expose the raw boolean; it reflects the flag only through the delegated inbox-list fragment, while the status-bar fragment ignores it.
- search-fragment effect: the [search fragment endpoint](../http/groom.md#get-search-fragment) renders only the inbox fragment and therefore can reflect the flag when `q` is empty and no gated workflows match; a non-empty `q` suppresses the loading placeholder even while the flag is true.
- startup completion effect: [startup background discovery scan](startup-background-discovery-scan.md) sets the flag false after its reconciliation attempt exits, including when reconciliation raises, then broadcasts the dashboard shell with the completed loading state.
- manual refresh start effect: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the flag true and broadcasts the dashboard shell before Docker reconciliation starts, so connected tabs can see the loading state before scan results arrive.
- manual refresh completion effect: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) sets the flag false after the reconciliation attempt exits; a successful refresh then broadcasts the completed shell and returns `ok: true` with the discovered workflow count.
- concurrency: no cross-process coordination, database, external broker, lock, reference count, or per-scan token participates; overlapping refreshes share the same process-local flag, so any refresh completion can clear the advertised loading state for the process.
- lifetime: resets to the initial value on process start and is lost on process exit.
- non-goal: the flag is presentation state only; it does not prove Docker is reachable, does not serialize scans, does not indicate that the workflow registry is complete, and does not change workflow, gate, sidecar, or browser selection data by itself.

## Fields

### field-value

- type: `bool`
- default: `True`
- required: true
- code: groom/groom/state.py::SCANNING
- meaning: current process-level discovery-loading state consumed by dashboard fragment renderers and mutated by startup and manual discovery orchestration.
- producer: module initialization creates the value before the server starts accepting requests; startup background discovery and manual refresh later assign boolean values directly.
- consumer: inbox empty-state rendering reads the value only after filtering leaves no matching inbox rows.
- visibility: user-visible only through rendered inbox fragments returned by HTTP search, rendered dashboard shell fragments, and websocket broadcasts; no HTTP response exposes the raw boolean as a standalone field.
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

- [method-render-empty-or-loading](../operator-inbox.md#method-render-empty-or-loading): reads the flag only when deciding how to render an empty inbox fragment; true plus empty query emits the loading placeholder, and false or any non-empty query emits the supplied empty text.
- [dashboard shell fragment](../dashboard-shell-fragment.md#field-discovery-scanning-flag-input): observes the flag indirectly through the delegated inbox renderer and never serializes the raw boolean as a field.
- [search fragment endpoint](../http/groom.md#get-search-fragment): observes the flag indirectly by calling the inbox renderer for an HTTP response that replaces only `#inbox-list`.
- [dashboard shell broadcaster](dashboard-shell-broadcaster.md): observes the flag indirectly by rendering the inbox as part of shell broadcasts after startup discovery, manual refresh start, manual refresh completion, sidecar updates, push updates, and answer handling.

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
- reader: `groom/groom/render.py::_empty_or_loading` is the only direct source reader; it reads the flag after inbox filtering has produced no rows.
- HTTP reader: `groom/groom/app.py::search` reaches the reader through `render.render_inbox` and returns the resulting inbox fragment without mutating the flag.
- websocket reader: `groom/groom/app.py::_broadcast_shell` reaches the reader through `render.render_shell_data` and `render.render_inbox` before enqueueing the shell fragment.
- startup writer: `groom/groom/app.py::_background_scan` clears the flag to `False` in its cleanup path.
- refresh writer: `groom/groom/app.py::refresh` sets the flag to `True` before its pre-scan broadcast and clears it to `False` in the reconciliation cleanup path.
- non-touchpoints: discovery scanning, Docker I/O, sidecar sessions, gate answering, workflow upsert/prune helpers, and static dashboard template serving do not read or assign the flag directly.
