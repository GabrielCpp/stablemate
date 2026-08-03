---
type: concept
slug: sidecar-connected-session
title: Sidecar connected session
---
# Sidecar connected session

Sidecar connected session is the per-websocket runtime owned by the [sidecar serving loop](sidecar-serving-loop.md). For one accepted [websocket-sidecar](../http/groom.md#websocket-sidecar) socket, it immediately advertises a `hello` [sidecar websocket frame](../sidecar-websocket-frame.md), delegates recursive workspace and runs watching to the [sidecar filesystem watch](sidecar-filesystem-watch.md), starts the [sidecar outbound sender](sidecar-outbound-sender.md) for filesystem-derived frames, serves host-issued data-plane RPC frames, and raises [ReloadRequested](groom-sidecar-module.md#concept-reloadrequested) so [sidecar live sessions](../sidecar-live-sessions.md) can restart the sidecar process.

- code: groom/groom/sidecar.py::_run_session
- verify: groom/tests/test_sidecar_session.py::test_run_session_advertises_hello_then_reload_raises

## Contract

- sig: `async _run_session(ws) -> None`
- input: `ws` is one already-connected websocket session object that supports `send(str)` and async iteration over inbound text frames.
- output: returns `None` only when inbound iteration ends without a reload request; raises the sidecar reload control exception when the host sends a reload frame.
- initial frame: sends exactly one `hello` [sidecar websocket frame](../sidecar-websocket-frame.md) before starting the watch task or consuming inbound frames.
- watched roots: asks the [sidecar filesystem watch](sidecar-filesystem-watch.md) to watch the configured workspace mount and configured runs mount recursively; absent roots are dropped rather than treated as session failure.
- outbound queue: creates one in-memory FIFO outbox for filesystem-derived `progress` and `blocked` frames and starts the [sidecar outbound sender](sidecar-outbound-sender.md) task that serializes each queued frame as websocket JSON text.
- inbound loop: consumes inbound websocket messages until the socket closes, ignoring raw payloads that fail JSON parsing and dispatching only mapping-like decoded messages whose `type` is `rpc` or `reload`.
- rpc behavior: a `rpc` frame is handled by [method-_handle_rpc](../sidecar-websocket-frame.md#method-_handle_rpc) against the same websocket before the next inbound frame is processed; the reply is a correlated `rpc_result` frame.
- reload behavior: a `reload` frame raises the reload control exception immediately; no `rpc_result`, acknowledgement, or terminal frame is sent for reload.
- event behavior: watched runs-file events enqueue a `progress` frame reflecting the latest current node; watched awaiting-gate files enqueue a `blocked` frame with workspace-relative path and extracted question; subdirectories created inside a watched tree are covered by the [sidecar filesystem watch](sidecar-filesystem-watch.md) without any further registration, and deletions are dropped.
- cleanup: always sets the shared stop event, then cancels and awaits both the watch task and the sender task while suppressing cancellation/socket-close errors, before leaving the session. Both are needed: the stop event lets the watch backend shut its own thread down cleanly, and the cancel covers the window before the next batch is yielded.
- non-effects: does not open or retry websocket connections, choose the websocket URI, close the websocket on reload, convert reload to a process exit code, mutate workflow state on the host, inspect Docker, write workspace files, or send residual HTTP pushes.
- errors: JSON decode/type/value errors raised while parsing an inbound raw payload are ignored; decoded values outside the mapping-like message contract are not converted into protocol errors by this layer; websocket send/iteration errors and unexpected watch or helper errors are not translated except for task cancellation during cleanup.

## Protocol Effects

- emits: one `hello` frame containing [sidecar identity data](../sidecar-identity-data.md) and [sidecar snapshot data](../sidecar-snapshot-data.md) at the start of the session.
- emits: zero or more `progress` frames when watched files under the runs mount change.
- emits: zero or more `blocked` frames when watched workspace files classify as awaiting operator gates.
- emits: one `rpc_result` frame for each supported, unknown, or handler-failing `rpc` request that reaches [method-_handle_rpc](../sidecar-websocket-frame.md#method-_handle_rpc) before session termination.
- consumes: `rpc` frames with `id`, `method`, and `params` fields from the host.
- consumes: `reload` frames from the host as a control message that unwinds the session.
- ignores: inbound frames that are not parseable JSON and parsed mapping-like messages whose `type` is neither `rpc` nor `reload`.
- requires: parsed inbound payloads are mapping-like message objects; valid JSON values outside that shape are outside the session contract rather than a supported ignored frame case.

## Filesystem Watch Contract

- workspace source: observes the sidecar workspace mount for gate context files and new subdirectories; heavy `.git`, `node_modules`, `__pycache__`, and `.venv` directories are excluded by the [sidecar filesystem watch](sidecar-filesystem-watch.md).
- runs source: observes the runs mount for workflow-progress writes; the emitted current-node value is read from the latest run checkpoint at event-processing time, not cached from connection start.
- directory events: directory create and move-in events do not emit a websocket frame; they only install watches below the new subtree so later file events can be observed.
- file events: non-directory events are classified into protocol frames by [method-_classify_event](../sidecar-websocket-frame.md#method-_classify_event); uninteresting files, unknown watch descriptors, unreadable gate files, or non-awaiting gate files produce no queued frame.
- queueing: filesystem-derived frames are put into the outbox without waiting for network I/O; websocket transmission is performed by the sender task.

## Algorithm

1. Serialize and send the current `hello` frame on the connected websocket.
2. Create the outbound frame queue and the shared stop event.
3. Install watches under the workspace mount and runs mount.
4. Start the [sidecar filesystem watch](sidecar-filesystem-watch.md) as its own task; the watch backend owns its thread, so nothing here blocks the loop.
5. Start the [sidecar outbound sender](sidecar-outbound-sender.md) task for queued filesystem frames.
6. Iterate inbound websocket text frames.
7. Ignore any inbound frame that cannot be decoded as JSON.
8. Dispatch `rpc` messages to [method-_handle_rpc](../sidecar-websocket-frame.md#method-_handle_rpc) and await its reply send.
9. Raise the reload control exception for a `reload` message.
10. On any exit path, set the stop event, then cancel and drain both the watch task and the sender task.

## Methods

### method-_run_session

- sig: `async _run_session(ws) -> None`
- abstract: false
- raises: [ReloadRequested](groom-sidecar-module.md#concept-reloadrequested) for a host `reload` frame; JSON parsing and expected sender cancellation cleanup are handled locally, while unexpected websocket, watch, classifier, RPC, or serialization failures can propagate.
- code: groom/groom/sidecar.py::_run_session
- verify: groom/tests/test_sidecar_session.py::test_run_session_advertises_hello_then_reload_raises
- input: one connected websocket object that can send JSON text frames and asynchronously yield inbound host text frames.
- output: returns `None` only when the websocket inbound iterator ends without a reload request or uncaught failure.
- effects: sends the initial `hello` frame, starts one watch task over the watchable workspace and runs mounts, starts one outbound sender task, consumes inbound frames, handles host RPCs, raises reload on request, and always attempts session cleanup.
- calls: [method-_hello_frame](../sidecar-websocket-frame.md#method-_hello_frame), [method-_watch_loop](sidecar-filesystem-watch.md#method-_watch_loop), [method-_sender_loop](sidecar-outbound-sender.md#method-_sender_loop), [method-_classify_event](../sidecar-websocket-frame.md#method-_classify_event), [method-_handle_rpc](../sidecar-websocket-frame.md#method-_handle_rpc), and [ReloadRequested](groom-sidecar-module.md#concept-reloadrequested).
- algorithm:
  1. Send one serialized `hello` frame built from fresh sidecar identity and snapshot data.
  2. Allocate the session's outbound FIFO queue and stop event.
  3. Recursively install watches under the configured workspace and runs mounts.
  4. Start the watch task, which yields coalesced change batches without blocking the loop.
  5. For directory create or move-in events, install watches below the new subtree and emit no frame.
  6. For non-directory events, classify the event and enqueue any resulting `progress` or `blocked` frame without awaiting websocket I/O.
  7. Start the outbound sender task that drains queued filesystem frames to the websocket.
  8. For each inbound host payload, ignore JSON decode/type/value failures raised while parsing the raw payload.
  9. Dispatch decoded `rpc` frames to the sidecar RPC handler and await its single reply send before consuming the next inbound frame.
  10. Raise the reload control signal immediately for decoded `reload` frames.
  11. During cleanup, set the stop event, then cancel and await the watch and sender tasks while suppressing expected cancellation/socket-close cleanup errors.

## Deeper Calls

- [Sidecar websocket frame](../sidecar-websocket-frame.md) defines the `hello`, `progress`, `blocked`, `rpc`, `rpc_result`, and `reload` messages this session emits or consumes.
- [Sidecar snapshot](sidecar-snapshot.md) supplies the state embedded in the initial `hello` frame through the hello-frame helper.
- [method-_hello_frame](../sidecar-websocket-frame.md#method-_hello_frame) builds the initial full-state advertise frame from fresh sidecar identity and snapshot data.
- [Sidecar filesystem watch](sidecar-filesystem-watch.md) watches the configured mounts recursively and feeds the session's outbound queue.
- [Sidecar outbound sender](sidecar-outbound-sender.md) drains the queued outbound filesystem frames to websocket text sends.
- [method-_classify_event](../sidecar-websocket-frame.md#method-_classify_event) translates watched filesystem events into `progress` and `blocked` frames.
- [method-_handle_rpc](../sidecar-websocket-frame.md#method-_handle_rpc) dispatches host-issued RPC frames to the sidecar data-plane readers and sends correlated success or failure result frames.
- [ReloadRequested](groom-sidecar-module.md#concept-reloadrequested) is the internal control signal raised for a host reload request and interpreted by the serving loop.
