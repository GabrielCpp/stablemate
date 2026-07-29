---
type: concept
slug: dashboard-resync-poller
title: Dashboard resync poller
---
# Dashboard resync poller

Dashboard resync poller is the [groom dashboard](../gui/screens/groom-dashboard.md)'s HTTP fallback: when the [dashboard connection state machine](dashboard-connection-state-machine.md) says the socket is not a trustworthy source of truth, the poller pulls [get dashboard state](../http/groom.md#get-dashboard-state) on an interval and feeds the body into the same `applyState()` a pushed frame goes through.

The design constraint that makes it worth a document is that the resync must not be a *second* rendering path. A fallback path only runs when something has already gone wrong, which is exactly when nobody is watching it — so a fallback that rendered differently would rot unobserved and be discovered by an operator during an incident. `GET /api/state` therefore returns the identical payload the socket pushes, built by the same [groom projection module](groom-projection-module.md) function, and lands in the identical store entry point. The resync is not a parallel path; it is the only path, reached a different way.

- code: groom/groom/assets/dashboard.js::resync
- code: groom/groom/assets/dashboard.js::startConnection
- refs: [dashboard connection state machine](dashboard-connection-state-machine.md), [dashboard client store](dashboard-client-store.md), [groom projection module](groom-projection-module.md), [dashboard state payload](../dashboard-state-payload.md)
- verify: groom/tests/test_dashboard_client.py::test_every_endpoint_is_read_as_json
- verify: groom/tests/test_connection_state.py::test_open_but_silent_socket_goes_stale_and_starts_resyncing
- verify: groom/tests/test_projection.py::test_state_message_is_json_serializable

## Contract

- purpose: keep a tab's fleet view current when the websocket is silent, closed, or lying, without introducing a second way of rendering state.
- trigger: the evaluator calls it whenever the derived connection carries `resyncing` and the previous resync is at least `RESYNC_EVERY_MS` (5000 ms) old — the same cadence as the server's push clock, so a degraded tab updates about as often as a healthy one.
- endpoint: `GET /api/state` with an explicit `accept: application/json` header.
- payload identity: the response body is byte-identical to what a pushed `state` frame carries. Both are `state_message` output.
- single entry point: the parsed body goes through `applyState()` — the same function `onFrame` calls for a pushed `state` — so there is one merge rule and one render path.
- reentrancy: an in-flight resync suppresses another. A slow response cannot stack requests, and a server that is slow rather than dead is not stampeded.
- failure handling: a network error is swallowed; offline stays offline and the next tick tries again. A non-`ok` response is discarded without applying anything, so an error page can never be parsed as a fleet.
- last-resync stamp: recorded only after a successful apply, so a failing fetch does not push the next attempt out by a full interval.
- visibility resync: returning to a backgrounded tab re-evaluates the connection immediately and forces one resync when the phase is not `live`, instead of showing a stale fleet for up to a full interval.
- scope: fleet-wide state only. The open run's detail is not resynced here — it is re-delivered by re-declaring the subscription in the [run watch registry](run-watch-registry.md) on the next socket open. Per-selection panels (files, diff, traces, repositories) are fetched by their own handlers on demand and are not part of a resync.
- excluded: the poller does not open or close sockets, send commands, decide phases, or write anything into the store beyond what `applyState()` writes.

## Fields

### field-resync-every-ms

- type: `number`
- default: 5000
- required: true
- meaning: minimum spacing between resyncs while degraded; matches the server's live tick so a resyncing tab is not visibly slower than a pushed one.

### field-resync-in-flight

- type: `boolean`
- default: false
- required: true
- meaning: the reentrancy guard. True from the moment a fetch starts until it settles, success or failure.

### field-last-resync-ts

- type: `number` (epoch milliseconds)
- default: 0
- required: true
- meaning: when the last *successful* resync applied; the interval check reads it.

## Methods

### method-resync

- sig: `async resync() -> void`
- abstract: false
- raises: none; network failures are caught and dropped.
- code: groom/groom/assets/dashboard.js::resync
- step: Return immediately if a resync is already in flight.
- step: Raise the in-flight guard.
- step: Fetch `/api/state` asking for JSON.
- step: On an `ok` response, parse the body and pass it to `applyState()`, then stamp the last-resync time.
- step: On a network error, do nothing — the next evaluation tick will try again.
- step: Lower the in-flight guard in all cases.

### method-start-connection

- sig: `startConnection() -> void`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::startConnection
- step: Open the websocket.
- step: Start the once-a-second connection evaluator, which is what schedules resyncs.
- step: Register a `visibilitychange` listener that re-evaluates on becoming visible and forces one resync when the phase is not `live`.

## Algorithms

### algorithm-degraded-tab-keeps-updating

- step: The socket goes silent past 15 seconds; the connection state machine returns `stale` with `resyncing` set.
- step: The chip changes so the operator can see the tab is no longer being pushed to.
- step: The next evaluation tick past the 5-second spacing calls the poller.
- step: The response — the same payload a push would have carried — goes through `applyState()`, and the fleet list, the status bar, and the scanning flag update exactly as if a frame had arrived.
- step: When a frame finally does arrive, recency is restored, the phase returns to `live`, and resyncing stops on the next tick. No reload, no lost selection, no second code path.

## Failure Semantics

- Server down: every fetch rejects, nothing is applied, the phase stays `offline`, and the displayed fleet is whatever was last known — labelled as such by the chip rather than presented as current.
- Error response: a non-`ok` status is discarded before parsing, so an HTML error page cannot be mistaken for a state payload.
- Slow server: the in-flight guard means at most one outstanding request per tab; requests do not queue behind a slow one.
- Recovery race: a push and a resync can both apply within the same second. Because both carry the whole fleet and go through the same merge, the later write simply wins and neither can leave a partially-updated list.
