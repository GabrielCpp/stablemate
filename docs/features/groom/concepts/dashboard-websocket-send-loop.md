---
type: concept
slug: dashboard-websocket-send-loop
title: Dashboard websocket send loop
---
# Dashboard websocket send loop

Dashboard websocket send loop is groom's per-browser-tab outbound websocket pump and the detailed helper for the [Groom app module send-loop member](groom-app-module.md#method-send-loop). The [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session) invocation starts one loop with the accepted browser websocket and that tab's queue from the [dashboard client queue set](dashboard-client-queue-set.md); broadcasts enqueue [dashboard shell fragments](../dashboard-shell-fragment.md), [blocked notification script fragments](../blocked-notification-script-fragment.md), or [groom answered script fragments](../groom-answered-script-fragment.md), and this loop serializes each queued string as one websocket text frame for the [groom dashboard](../gui/screens/groom-dashboard.md). It is paired with the [dashboard websocket receive loop](dashboard-websocket-receive-loop.md), but it only owns server-to-browser delivery.

- code: groom/groom/app.py::_send_loop

## Contract

- sig: `async _send_loop(socket: WebSocket, queue: asyncio.Queue) -> None`
- purpose: forward every outbound dashboard fragment accepted by one registered client queue to that same client's websocket connection as a text frame.
- owner: [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session); the session accepts the socket, creates and registers the queue, starts this loop as a task, and removes the queue during cleanup.
- counterpart: [dashboard websocket receive loop](dashboard-websocket-receive-loop.md); receive-side completion or failure can cause the owning session to cancel this send loop.
- input socket: accepted browser dashboard websocket; required; default none; not created, accepted, closed, or unregistered by this layer.
- input queue: `asyncio.Queue`; required; default none; normally the [dashboard client queue](dashboard-client-queue-set.md#field-client-queue) registered for exactly one browser tab.
- payload type: string; each queue item is treated as a complete websocket text-frame body.
- payload producers: [broadcast dashboard fragment](dashboard-client-queue-set.md#method-broadcast-dashboard-fragment) calls enqueue already-rendered shell and script fragments; this loop does not know which producer enqueued a particular item.
- output: no normal return value; the coroutine is intentionally long-running and only stops through cancellation or an exception from queue retrieval or websocket sending.
- ordering: preserves per-queue FIFO delivery because each frame is sent only after the previous `queue.get()` result has been sent.
- backpressure: waits for the websocket send operation to complete before reading the next queue item; it does not batch, coalesce, skip, or retry items.
- errors: exceptions from queue retrieval, websocket send, transport closure, or task cancellation propagate to the task owner; the loop does not convert them to domain result values, acknowledgement frames, HTTP responses, browser events, or log entries.

## Methods

### method-send-queued-dashboard-fragments

- sig: `async _send_loop(socket: WebSocket, queue: asyncio.Queue) -> None`
- abstract: false
- raises: propagates cancellation, queue-get failures, websocket send failures, and transport closure exceptions.
- code: groom/groom/app.py::_send_loop

#### Inputs

- socket: accepted dashboard `WebSocket`; required; default none; must already be ready for text sends because the session accepted it before starting the loop.
- queue: `asyncio.Queue`; required; default none; contains server-rendered outbound payload strings for the same browser session.
- queue membership: the queue may or may not still be present in the [dashboard client queue set](dashboard-client-queue-set.md) while the loop is waiting; registration affects future broadcasts, not this loop's ability to consume already queued items.
- item value: each `queue.get()` result is expected to be a string fragment; no first-party validation or conversion is performed before sending it.

#### Algorithm

- step: Enter an unbounded wait/send cycle for the supplied queue and websocket.
- step: Await one item from the queue.
- step: Treat the item as the exact outbound websocket text payload.
- step: Await one websocket text send of that exact payload.
- step: Return to waiting for the next queue item only after the send operation completes.
- step: End only when cancellation, queue access, websocket transport, or send operation raises to the owning dashboard websocket session.

#### Effects

- Reads: removes exactly one queued payload at a time from the supplied queue.
- Emits: sends exactly one websocket text frame per successfully read queue item.
- Ordering: never starts sending item N+1 before item N's `send_text` operation completes.
- Payload preservation: sends the queued payload unchanged; no rendering, escaping, wrapping, command discrimination, deduplication, truncation, or script filtering happens in this layer.
- Empty queue: waits without sending frames, registering clients, rendering placeholders, or timing out.
- Failure: if a send fails after the payload was removed from the queue, this layer does not requeue, retry, broadcast to other queues, or synthesize a failure frame; the exception belongs to the owning websocket session.
- Does not: inspect inbound browser frames, answer gate files, append answer logs, mutate the [workflow registry](workflow-registry.md), mutate the [dashboard client queue set](dashboard-client-queue-set.md), cancel the sibling receive loop, unregister the queue, decide websocket session lifetime, or persist outbound data outside process memory.
- Bottoms out: this layer calls only the supplied queue's receive abstraction and the framework websocket text-send abstraction; it calls no further first-party groom symbol.

## Algorithm

- step: Receive an accepted dashboard websocket and one per-session outbound queue from the surrounding websocket session.
- step: Block until a broadcast has queued one HTML/script payload for this browser session.
- step: Send that payload as one websocket text frame to the browser dashboard.
- step: Repeat the queue-read and text-send sequence for the life of the task.
- step: Let cancellation, websocket disconnect/send failure, or queue failure propagate so the surrounding session can cancel the sibling receive task and unregister the queue.

## Effects

- Repeats indefinitely while the task remains active.
- Reads exactly one queued item at a time from the supplied queue.
- Treats the queued item as the complete websocket text payload; no rendering, escaping, validation, wrapping, or event classification happens in this layer.
- Sends the queued payload on the supplied websocket with text-frame semantics.
- Emits no acknowledgement frame, log entry, metric, HTTP response, sidecar RPC, or additional dashboard broadcast.
- Mutates neither the [dashboard client queue set](dashboard-client-queue-set.md) membership nor any [workflow registry](workflow-registry.md) state.
- Does not inspect inbound browser frames, answer gate files, cancel its sibling receive loop, unregister the queue, or decide websocket session lifetime; those effects belong to the surrounding [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session) invocation.
- Bottoms out in the provided queue and websocket abstractions; it calls no other first-party groom symbol.

## Failure Semantics

- Cancellation: task cancellation interrupts whichever queue wait or websocket send is in progress and propagates to the owning session; the loop has no cleanup branch of its own.
- Websocket disconnect or send failure: the failed send raises out of the loop; any already sent frames remain sent, and the failed payload is not retried or requeued by this layer.
- Queue failure: an exception from queue retrieval raises out of the loop before any frame is emitted for that failed retrieval.
- Completed sibling receive loop: the loop does not observe the sibling task directly; the owning websocket session cancels this task when the receive task completes first.
- No clients: not represented inside this loop. A loop instance exists only after a dashboard websocket session has accepted a client and supplied its queue.
