---
type: concept
slug: dashboard-connection-state-machine
title: Dashboard connection state machine
---
# Dashboard connection state machine

Dashboard connection state machine is the client-side rule that decides whether the [groom dashboard](../gui/screens/groom-dashboard.md) is currently being told the truth. It has four phases — `live`, `stale`, `reconnecting`, `offline` — and it derives them from **message recency, not `WebSocket.readyState`**.

That distinction is the whole reason the unit exists. A half-open TCP socket reads `OPEN` forever and will never deliver another frame. A dashboard that trusts `readyState` therefore shows a green dot over a frozen fleet, and the operator's most load-bearing signal — "is anything blocked right now?" — silently becomes a screenshot of the past. The server ticks every `GROOM_LIVE_TICK_S` (5s) whether or not anything changed, precisely so that silence carries information: three missed ticks is not a quiet fleet, it is a broken pipe.

The rule is a pure function of observations, so it can be asserted against synthetic timestamps rather than against a real socket. The phase it returns drives two things: the connection chip the operator can see, and the `resyncing` flag the [dashboard resync poller](dashboard-resync-poller.md) acts on.

- code: groom/groom/assets/dashboard.js::deriveConnection
- code: groom/groom/assets/dashboard.js::backoffDelay
- code: groom/groom/assets/dashboard.js::evaluateConnection
- code: groom/groom/assets/dashboard.js::ConnectionChip
- refs: [dashboard resync poller](dashboard-resync-poller.md), [dashboard client store](dashboard-client-store.md), [groom dashboard](../gui/screens/groom-dashboard.md)
- verify: groom/tests/test_connection_state.py::test_open_socket_receiving_frames_is_live
- verify: groom/tests/test_connection_state.py::test_open_but_silent_socket_goes_stale_and_starts_resyncing
- verify: groom/tests/test_connection_state.py::test_a_closed_socket_reconnects_then_goes_offline
- verify: groom/tests/test_connection_state.py::test_the_full_live_to_stale_to_offline_progression
- verify: groom/tests/test_connection_state.py::test_backoff_grows_and_is_capped
- verify: groom/tests/test_connection_state.py::test_source_defines_the_thresholds_the_harness_extracts

## Contract

- purpose: classify the browser's confidence in its own view of the fleet, and say whether HTTP has to carry the tab.
- input: an observation object `{now, socketOpen, lastMessageTs, closedSince}` — four numbers and a boolean, all supplied by the caller.
- output: `{phase, resyncing}`; nothing else is returned and nothing is mutated.
- purity: `deriveConnection` reads no clock, no socket, and no store. The evaluator that calls it every second is what supplies wall time.
- recency, not readiness: an open socket is `live` only while its last frame is recent. `readyState` is consulted to know whether a socket is open at all, never to conclude that it is working.
- threshold derivation: `STALE_AFTER_MS` (15s) is three ticks of the server's 5s clock and `OFFLINE_AFTER_MS` (60s) is twelve. Both are generous multiples so one slow push or one dropped frame cannot flap the chip. Both are exported from the module, and the test harness extracts them from the source rather than restating them, so a change to the constants cannot leave the tests asserting the old policy.
- resyncing semantics: anything but `live` sets `resyncing`. The flag means "the socket is not a trustworthy source of truth", not "the socket is closed" — which is why `stale`, whose socket is still open, resyncs too.
- reconnect policy: on close, a reconnect is scheduled with exponential backoff — `500ms × 2^attempt`, capped at 30s — and the attempt counter resets to zero on a successful open.
- open is not live: on socket open the last-message timestamp is stamped but the phase is not forced. The server's first frame is what proves the connection carries data, and that is what `live` is allowed to mean.
- subscription re-declaration: the server forgets a tab the moment it drops, so the open handler re-sends `{cmd: "watch", run_id}` for the currently selected run. That is what makes a reconnect self-healing: the server answers with the current detail and an open pane recovers without a fetch and without the operator touching anything.
- store writes: the evaluator writes the phase into the [dashboard client store](dashboard-client-store.md) only when it actually changed, so a steady `live` connection does not re-render the chip once a second.
- visibility: a tab returning from the background has usually missed ticks; `visibilitychange` re-evaluates immediately and forces a resync when the phase is not `live`, rather than showing a stale fleet for up to a full interval.
- excluded: the machine does not open, close, or reconnect the socket itself, does not send frames, does not fetch, and does not touch the sidecar socket — which has its own lifecycle and is not folded into this one.

## Fields

### field-stale-after-ms

- type: `number` (exported constant)
- default: 15000
- required: true
- code: groom/groom/assets/dashboard.js::STALE_AFTER_MS
- meaning: how long an open socket may go silent before the tab stops believing it. Three server ticks.

### field-offline-after-ms

- type: `number` (exported constant)
- default: 60000
- required: true
- code: groom/groom/assets/dashboard.js::OFFLINE_AFTER_MS
- meaning: how long a closed socket may stay closed before the tab stops describing itself as reconnecting and settles into interval resync.

### field-eval-every-ms

- type: `number`
- default: 1000
- required: true
- meaning: how often the phase is recomputed. Fast enough that the chip reacts within a second of a threshold crossing, cheap enough that the recompute is four comparisons.

### field-backoff-bounds

- type: `number` pair
- default: base 500, max 30000
- required: true
- meaning: the exponential reconnect schedule. Capped so a server that is down for an hour is still retried twice a minute rather than once an aeon.

### field-connection-phase

- type: one of `live`, `stale`, `reconnecting`, `offline` (plus the initial `connecting` the store starts at)
- default: `connecting` until the first evaluation runs
- required: true
- meaning: the value the connection chip displays and the store holds.

## Methods

### method-derive-connection

- sig: `deriveConnection(obs) -> {phase, resyncing}`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::deriveConnection
- step: If the socket is open, compute silence as `now - lastMessageTs`.
- step: Silence within `STALE_AFTER_MS` → `{phase: "live", resyncing: false}`.
- step: Silence past it → `{phase: "stale", resyncing: true}` — open, but not believed.
- step: If the socket is closed and it closed within `OFFLINE_AFTER_MS` → `{phase: "reconnecting", resyncing: true}`; a backoff attempt is already in flight.
- step: Closed longer → `{phase: "offline", resyncing: true}`.

### method-backoff-delay

- sig: `backoffDelay(attempt) -> number`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::backoffDelay
- step: Return `min(BACKOFF_MAX_MS, BACKOFF_BASE_MS × 2^attempt)`.

### method-evaluate-connection

- sig: `evaluateConnection() -> void`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::evaluateConnection
- step: Build an observation from wall time and the connection singleton's open flag, last-message timestamp, and closed-since timestamp.
- step: Derive the next phase.
- step: Write it into the store only if the phase or the resyncing flag differs from what is already there.
- step: If resyncing and the last resync is at least `RESYNC_EVERY_MS` old, ask the [dashboard resync poller](dashboard-resync-poller.md) to pull.

## Algorithms

### algorithm-half-open-socket-detection

- step: The server pushes a `state` frame every 5 seconds regardless of whether anything changed.
- step: Every inbound frame stamps `lastMessageTs`, whatever its type.
- step: The evaluator runs once a second and compares that stamp to now.
- step: A socket whose transport has died but whose `readyState` still reads `OPEN` stops stamping, crosses 15 seconds of silence, and is classified `stale`.
- step: The chip changes to `stale` and HTTP resync starts carrying the tab, so the fleet keeps updating over a socket that will never deliver another frame.

## Failure Semantics

- Unparseable frame: a frame that fails `JSON.parse` is dropped without stamping recency — a frame that cannot be acted on is not evidence the connection works.
- Reconnect storm: guarded by the attempt counter and the 30s cap; a closed handler for a socket that is no longer the current one returns without scheduling a duplicate reconnect.
- Server restart: the tab reconnects on backoff, receives a fresh full `state` snapshot as the first frame, and re-declares its watch, so it converges without a page reload.
- Permanently dead server: the phase settles at `offline` and the resync poller's fetches fail; the chip keeps saying `offline` rather than any phase that would imply the view is current.
