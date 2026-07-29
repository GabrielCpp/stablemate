---
type: concept
slug: dashboard-websocket-receive-loop
title: Dashboard websocket receive loop
---
# Dashboard websocket receive loop

Dashboard websocket receive loop is groom's per-browser-tab inbound websocket pump and the detailed helper for the [Groom app module recv-loop member](groom-app-module.md#method-recv-loop). The [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session) invocation starts one loop with the accepted browser websocket; the loop receives decoded browser JSON messages from the [groom dashboard](../gui/screens/groom-dashboard.md) and delegates each message — together with that tab's own outbound queue — to the dashboard command handler that consumes [dashboard websocket command frames](../dashboard-websocket-answer-frame.md). It is the inbound counterpart to the [dashboard websocket send loop](dashboard-websocket-send-loop.md): the receive loop owns browser-to-server frames, while the send loop owns queued server-to-browser messages.

The queue is threaded through because one of the two commands is per-tab. `watch` records this tab's open run in the [run watch registry](run-watch-registry.md), which is keyed by queue — so the handler needs to know *which* client spoke, something a fleet-wide broadcaster never has to.

- code: groom/groom/app.py::_recv_loop

## Contract

- sig: `async _recv_loop(socket: WebSocket, queue: asyncio.Queue) -> None`
- purpose: keep one accepted dashboard websocket session listening for inbound browser JSON messages and dispatch every decoded value, with this tab's outbound queue, to the dashboard command handler.
- socket: Litestar `WebSocket`; required; default none; already accepted by the surrounding [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session); not created, accepted, closed, or unregistered by this loop.
- queue: `asyncio.Queue`; required; default none; this tab's registered outbound queue, passed through untouched so the command handler can identify the client and reply to it alone.
- input-frame: one JSON value decoded from each inbound websocket message by the websocket layer; first-party dashboard code sends objects matching [dashboard websocket command frame](../dashboard-websocket-answer-frame.md).
- accepted first-party commands: a JSON object whose `cmd` field is exactly `"answer"` or `"watch"`; this loop does not inspect that discriminator and relies on the command handler for command-level effects.
- unknown command: a JSON object with any other `cmd` value is still delivered to the command handler; the command handler returns without state mutation, log entry, gate write, response frame, or broadcast.
- non-object frame: a decoded JSON value that is not mapping-like is passed unchanged to the command handler; because the handler expects `.get(...)`, this is outside the first-party contract and raises from the delegated handler rather than producing an error payload.
- output: no normal return value; the coroutine is intentionally long-running and stops only when receiving, decoding, command handling, cancellation, or websocket closure raises or completes through the websocket abstraction.
- ordering: preserves inbound receive order for this one websocket session because the next receive is not attempted until the current decoded value has been fully handled.
- concurrency: serializes commands from one browser tab; separate dashboard websocket sessions each run their own receive loop and may handle inbound frames concurrently through shared process-local state.
- task boundary: created by the surrounding websocket session as a sibling of the outbound send loop; this loop does not create, cancel, await, or inspect its sibling task.
- errors: receive/decode exceptions, command-handler exceptions, websocket disconnects, and task cancellation propagate to the task owner; the loop does not convert them to acknowledgement frames, HTTP responses, browser events, or domain result values.

## Algorithm

- Repeat while the task remains active.
- Await one decoded JSON value from the supplied websocket through the websocket receive abstraction.
- Await the dashboard command handler with that exact decoded value and this session's outbound queue.
- Resume waiting for the next inbound websocket message only after the command handler finishes successfully.
- End only by propagated cancellation, websocket close/disconnect, receive/decode failure, or command-handler failure.

## Effects

- Receives exactly one decoded JSON message from the supplied websocket at a time.
- Passes the decoded message and the session queue unchanged to the dashboard command handler; this layer performs no command discrimination, field normalization, schema validation, object-type guard, logging, or state mutation itself.
- Waits for the command handler to finish before receiving another inbound frame, so one websocket session does not process two inbound dashboard commands concurrently through this loop.
- Sends no response frame, acknowledgement frame, browser event script, HTTP response, sidecar RPC, or additional dashboard broadcast on its own.
- Mutates neither the [dashboard client queue set](dashboard-client-queue-set.md) membership nor any [workflow registry](workflow-registry.md) state directly.
- Does not inspect outbound broadcast queues, send queued dashboard messages, cancel its sibling send loop, unregister the queue, or decide websocket session lifetime; those effects belong to the surrounding [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session) invocation.
- Calls the first-party [dashboard command handler](groom-app-module.md#method-handle-command) `groom/groom/app.py::_handle_command`; that handler is already grounded by the [dashboard websocket command frame](../dashboard-websocket-answer-frame.md), [answer log entry](../answer-log-entry.md), [run watch registry](run-watch-registry.md), [workflow state](workflow-state.md#transition-successful-last-gate-answer), and dashboard answer interaction nodes, so this layer reveals no additional undocumented first-party callee.
- Bottoms out at the third-party websocket receive abstraction and the already-documented first-party command handler; standard library task cancellation and websocket-framework disconnect behavior are described only as propagated boundaries, not as deeper groom layers.
