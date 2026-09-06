---
type: concept
slug: dashboard-websocket-send-loop
title: Dashboard websocket send loop
---
# Dashboard websocket send loop

Dashboard websocket send loop is groom's per-browser-tab outbound websocket pump and the detailed helper for the [Groom app module send-loop member](groom-app-module.md#method-send-loop). The [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session) starts one loop with the accepted browser websocket and that tab's queue from the [dashboard client queue set](dashboard-client-queue-set.md). Broadcasts and per-run pushes enqueue projected messages such as a [dashboard state payload](../dashboard-state-payload.md), `detail`, `notify`, or `answered`; this loop is the single place the queued value becomes JSON text and then one websocket text frame for the [groom dashboard](../gui/screens/groom-dashboard.md). It is paired with the [dashboard websocket receive loop](dashboard-websocket-receive-loop.md), but owns server-to-browser delivery only.

- code: groom/groom/app.py::_send_loop

## Contract

- sig: `async _send_loop(socket: WebSocket, queue: asyncio.Queue) -> None`
- purpose: forward every outbound dashboard message accepted by one registered client queue to that same client's websocket connection as a text frame.
- owner: [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session); the session accepts the socket, creates and registers the queue, starts this loop as a task, and removes the queue during cleanup.
- counterpart: [dashboard websocket receive loop](dashboard-websocket-receive-loop.md); receive-side completion or failure can cause the owning session to cancel this send loop.
- input socket: accepted browser dashboard websocket; required; default none; not created, accepted, closed, or unregistered by this layer.
- input queue: `asyncio.Queue`; required; default none; normally the [dashboard client queue](dashboard-client-queue-set.md#field-client-queue) registered for exactly one browser tab.
- payload type: any JSON-serializable value; first-party producers enqueue `dict` messages, and each queue item is JSON-serialized here to form the complete websocket text-frame body. The loop does not validate or discriminate the value before serialization.
- payload producers: [broadcast dashboard message](dashboard-client-queue-set.md#method-broadcast-dashboard-message) enqueues fleet-wide messages and the [run watch registry](run-watch-registry.md) path enqueues per-run `detail` messages; this loop does not know which producer enqueued a particular item, and does not read its `type`.
- output: no normal return value; the coroutine is intentionally long-running and only stops through cancellation or an exception from queue retrieval, JSON serialization, or websocket sending.
- ordering: preserves per-queue FIFO delivery because each frame is sent only after the previous `queue.get()` result has been sent.
- backpressure: waits for the websocket send operation to complete before reading the next queue item; it does not batch, coalesce, skip, or retry items.
- errors: exceptions from queue retrieval, websocket send, transport closure, or task cancellation propagate to the task owner; the loop does not convert them to domain result values, acknowledgement frames, HTTP responses, browser events, or log entries.

## Methods

### method-send-queued-dashboard-messages

- sig: `async _send_loop(socket: WebSocket, queue: asyncio.Queue) -> None`
- abstract: false
- does: waits for one queued outbound value when the queue is empty.
- verify: emitted(event="dashboard websocket text frame", count=1)
- does: removes one queued outbound value before serializing it.
- verify: emitted(event="dashboard websocket text frame", count=1)
- does: serializes the removed value with `json.dumps` as the complete websocket text payload.
- verify: emitted(event="dashboard websocket text frame", count=1)
- does: sends the serialized payload as one text frame before reading the next queue value.
- verify: emitted(event="dashboard websocket text frame", count=1)
- raises: propagates cancellation from the queue wait or websocket send.
- raises: propagates queue retrieval failures without emitting a frame for that retrieval.
- raises: propagates JSON serialization and websocket send failures without retrying or requeueing the removed value.
- returns: never returns normally; it repeats until cancellation or an exception exits the coroutine.
- code: groom/groom/app.py::_send_loop

#### Inputs

- socket: accepted dashboard `WebSocket`; required; default none; must already be ready for text sends because the session accepted it before starting the loop.
- queue: `asyncio.Queue`; required; default none; contains already-projected outbound message objects for the same browser session.
- queue membership: the queue may or may not still be present in the [dashboard client queue set](dashboard-client-queue-set.md) while the loop is waiting; registration affects future broadcasts, not this loop's ability to consume already queued items.
- item value: each `queue.get()` result must be JSON-serializable for a send to succeed; no first-party validation, schema check, or `type` discrimination occurs before serialization.

#### Algorithm

- step: Enter an unbounded wait/send cycle for the supplied queue and websocket.
- step: Await one item from the queue.
- step: Serialize the item with `json.dumps` to produce the outbound websocket text payload.
- step: Await one websocket text send of that payload.
- step: Return to waiting for the next queue item only after the send operation completes.
- step: End only when cancellation, queue access, websocket transport, or send operation raises to the owning dashboard websocket session.

#### Effects

- Reads: removes exactly one queued message at a time from the supplied queue.
- Emits: sends exactly one websocket text frame per successful queue retrieval and send.
- Ordering: never starts sending item N+1 before item N's `send_text` operation completes.
- Payload preservation: serializes the queued object and sends the result unchanged; no projection, wrapping, envelope, command discrimination, deduplication, or truncation happens in this layer. The object is shared with every other tab in the same broadcast, so it is read and never mutated.
- Empty queue: waits without sending frames, registering clients, rendering placeholders, or timing out.
- Failure: if serialization or the send fails after the message was removed from the queue, this layer does not requeue, retry, broadcast to other queues, or synthesize a failure frame; the exception belongs to the owning websocket session. The tab recovers through the [dashboard resync poller](dashboard-resync-poller.md).
- Does not: inspect inbound browser frames, answer gate files, append answer logs, mutate the [workflow registry](workflow-registry.md), mutate the [dashboard client queue set](dashboard-client-queue-set.md), cancel the sibling receive loop, unregister the queue, decide websocket session lifetime, or persist outbound data outside process memory.
- Bottoms out: this layer calls only the supplied queue's receive abstraction and the framework websocket text-send abstraction; it calls no further first-party groom symbol.

## Failure Semantics

- Cancellation: task cancellation interrupts whichever queue wait or websocket send is in progress and propagates to the owning session; the loop has no cleanup branch of its own.
- Websocket disconnect or send failure: the failed send raises out of the loop; any already sent frames remain sent, and the failed message is not retried or requeued by this layer.
- Queue failure: an exception from queue retrieval raises out of the loop before any frame is emitted for that failed retrieval.
- Completed sibling receive loop: the loop does not observe the sibling task directly; the owning websocket session cancels this task when the receive task completes first.
- No clients: not represented inside this loop. A loop instance exists only after a dashboard websocket session has accepted a client and supplied its queue.
