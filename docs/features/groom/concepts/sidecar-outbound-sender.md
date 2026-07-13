---
type: concept
slug: sidecar-outbound-sender
title: Sidecar outbound sender
---
# Sidecar outbound sender

Sidecar outbound sender is the queue-draining task owned by one [sidecar connected session](sidecar-connected-session.md). It consumes filesystem-derived outbound [sidecar websocket frame](../sidecar-websocket-frame.md) objects from the session's FIFO outbox, serializes each frame as JSON text, and sends that text on the already-connected websocket until the task is cancelled or the websocket send path fails. It is the sidecar-process counterpart to the host-side [sidecar connection](sidecar-connection.md): this sender writes sidecar-to-groom filesystem notifications, while the host-side connection writes groom-to-sidecar `rpc` and `reload` frames. It is the only sidecar layer that turns queued inotify-derived `progress` and `blocked` frame objects into websocket text delivery; the connected session owns queue creation, event classification, task cancellation, and socket lifetime.

- code: groom/groom/sidecar.py::_sender_loop

## Contract

- sig: `async _sender_loop(ws, outbox: asyncio.Queue) -> None`
- input: `ws` is the connected websocket object for the current [sidecar connected session](sidecar-connected-session.md), and must accept `send(str)` calls.
- input: `outbox` is the session-owned FIFO queue containing JSON-compatible frame dictionaries produced from watched filesystem events.
- output: no ordinary return while the task is allowed to run; the loop is intentionally open-ended and is stopped by task cancellation or by an exception from queue receive, JSON serialization, or websocket send.
- effects: waits for the next queued frame, serializes that frame to a websocket text payload, and sends it on the connected websocket before waiting for the next frame.
- queue rule: frames are removed from the outbox exactly once by `outbox.get()`; the sender does not mark task completion, requeue failed frames, drop stale frames, coalesce frames, inspect frame type, or add ordering metadata.
- admission rule: any object yielded by the outbox is treated as the complete outbound frame payload; the sender does not require a mapping, check `type`, restrict frame variants, validate required fields, or distinguish `progress` from `blocked` before serialization.
- ordering: send attempts follow the order in which frames become available from the FIFO queue; a later frame is not read until the previous frame has been serialized and its websocket send has completed.
- backpressure: websocket send latency delays the next queue read, so queued frames remain in the outbox until all earlier frames have completed serialization and send.
- serialization: every queued frame is encoded as ordinary JSON text matching the [sidecar websocket frame](../sidecar-websocket-frame.md) contract; the sender does not validate protocol fields before serialization.
- send contract: each accepted frame causes exactly one `ws.send(<json text>)` attempt; the sender does not use websocket JSON helpers, split a frame across messages, batch multiple frames into one message, or wait for application-level acknowledgement.
- lifecycle: the containing session starts one sender task after installing inotify readers and cancels it during session cleanup.
- cancellation: cancellation while waiting for a queued frame or while sending unwinds the task through normal async cancellation; the containing session suppresses that cancellation during cleanup.
- non-effects: does not create the queue, populate the queue, classify filesystem events, install watches, read files, parse inbound host frames, handle RPCs, send the initial `hello` frame, reconnect sockets, close sockets, send residual HTTP pushes, mutate workflow state, or decide sidecar process exit codes.
- boundary: sends only sidecar-to-groom queued filesystem frames; groom-to-sidecar `rpc` and `reload` writes belong to [sidecar connection](sidecar-connection.md), and sidecar-originated `rpc_result` replies bypass this queue through the inbound RPC handler.
- error handling: this layer adds no local exception translation; JSON serialization errors, websocket send failures, and queue failures propagate to the task caller unless the containing session suppresses them during cleanup.

## Algorithm

1. Wait until the outbox yields the next queued outbound frame.
2. Serialize that frame as JSON text.
3. Send the serialized text on the connected websocket.
4. Repeat from the next queue read without a terminal condition of its own.

## Methods

### method-_sender_loop

- sig: `async _sender_loop(ws, outbox: asyncio.Queue) -> None`
- abstract: false
- raises: no intentional domain exception; async cancellation, JSON serialization failures, websocket send failures, and queue failures can escape.
- code: groom/groom/sidecar.py::_sender_loop
- input: one connected websocket sender and the current session's outbound frame queue.
- output: no normal result; task lifetime is governed by the owning session.
- effects: drains queued frame objects one at a time and emits each as one JSON websocket text frame.
- calls: standard-library JSON serialization and the websocket object's send operation only; it does not call another Groom service symbol.
