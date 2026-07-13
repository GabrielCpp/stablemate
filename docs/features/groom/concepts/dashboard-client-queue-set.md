---
type: concept
slug: dashboard-client-queue-set
title: Dashboard client queue set
---
# Dashboard client queue set

Dashboard client queue set is groom's process-local fan-out target for browser dashboard websocket broadcasts. The [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session) invocation registers one outbound queue per connected tab, the [dashboard shell broadcaster](dashboard-shell-broadcaster.md), [sidecar blocked applier](sidecar-blocked-applier.md), and push/answer paths enqueue rendered HTML fragments through [broadcast dashboard fragment](#method-broadcast-dashboard-fragment), and the [dashboard websocket send loop](dashboard-websocket-send-loop.md) turns each queued fragment into a websocket text frame for the corresponding tab.

- code: groom/groom/state.py::CLIENTS
- refs: [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session), [dashboard websocket send loop](dashboard-websocket-send-loop.md), [dashboard shell broadcaster](dashboard-shell-broadcaster.md), [sidecar blocked applier](sidecar-blocked-applier.md), [dashboard shell fragment](../dashboard-shell-fragment.md)

## Contract

- scope: one in-memory set per groom process; it is shared by HTTP handlers, websocket handlers, and sidecar event handling inside that process.
- member type: `asyncio.Queue`; each queue is created as an unbounded default queue by one accepted browser dashboard websocket session and does not represent a sidecar websocket.
- lifetime: starts empty on process start, gains a queue after a dashboard websocket is accepted, loses that queue during websocket cleanup, and is lost entirely on process exit.
- delivery model: best-effort in-process queueing; a successful broadcast means every queue present in the broadcast snapshot accepted the fragment, not that any browser has already received, swapped, or executed it.
- ordering: fragments are enqueued to each individual queue in caller order when callers await broadcasts sequentially; the set does not define a global client ordering.
- snapshot rule: a broadcast targets the clients in a copied list of the set at the start of that broadcast pass; clients registered or removed after the copy do not alter that pass.
- concurrency rule: membership changes and broadcast queue writes use plain in-process objects with no registry-level lock, version, transaction, or retry; concurrent coroutines observe whichever set contents exist when their own operation runs, and the copied broadcast target list is the only isolation boundary.
- payload rule: the queue set accepts one already-rendered HTML string and does not inspect whether it is a [dashboard shell fragment](../dashboard-shell-fragment.md), script fragment, notification, or mixed payload.
- initial snapshot rule: the newly accepted browser websocket receives its first shell snapshot by a direct websocket text send before the send and receive tasks are started; that first snapshot is not enqueued through this set, while any concurrent later broadcasts can enqueue to the already-registered queue.
- persistence: no broker, database, cross-process coordination, replay buffer, or durable notification store participates.

## Callers

- dashboard websocket registration: [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session) creates one unbounded queue after accepting `/ws`, registers it with [register dashboard client](#method-register-dashboard-client), sends the first shell snapshot directly to the socket, starts the [dashboard websocket send loop](dashboard-websocket-send-loop.md), and unregisters the same queue in cleanup through [unregister dashboard client](#method-unregister-dashboard-client).
- shell convergence broadcasts: [dashboard shell broadcaster](dashboard-shell-broadcaster.md) calls [broadcast dashboard fragment](#method-broadcast-dashboard-fragment) after rendering a current out-of-band shell fragment for refresh, progress, exited, sidecar hello, sidecar progress, and startup scan paths.
- blocked notifications: [receive blocked push](../http/groom.md#receive-blocked-push) and [sidecar blocked applier](sidecar-blocked-applier.md) render the shell, append a notification script fragment, and call [broadcast dashboard fragment](#method-broadcast-dashboard-fragment) directly so every registered browser tab receives one combined payload.
- answered events: [send detail answer](../gui/screens/groom-dashboard.md#send-detail-answer) reaches the dashboard answer handler, which renders the shell, appends the `groom:answered` script only on successful gate answers, and calls [broadcast dashboard fragment](#method-broadcast-dashboard-fragment) directly.
- excluded callers: `/search`, `/repos`, file/diff/detail panel endpoints, sidecar data-plane RPC replies, and sidecar reload commands do not register dashboard browser queues or enqueue dashboard-client fragments through this set.

## Fields

### field-client-set

- type: `set[asyncio.Queue]`
- default: empty set at process import/startup
- required: true
- code: groom/groom/state.py::CLIENTS
- meaning: the current process-local membership of dashboard browser outbound queues eligible for future broadcasts.

### field-client-queue

- type: `asyncio.Queue`
- default: none
- required: true for membership
- meaning: one outbound fragment queue owned by one dashboard websocket connection.
- ownership: created by the dashboard websocket session after accepting the browser socket and consumed by one [dashboard websocket send loop](dashboard-websocket-send-loop.md).
- capacity: unbounded default `asyncio.Queue()` capacity for queues created by the dashboard websocket session.

## Methods

### method-register-dashboard-client

- sig: `add_client(queue: asyncio.Queue) -> None`
- abstract: false
- raises: none intentionally raised by the registry operation.
- code: groom/groom/state.py::add_client

Adds one websocket outbound queue to the process-local client set. Adding the same queue again is idempotent because membership is set-based.

#### Inputs

- queue: an `asyncio.Queue` object created for one accepted dashboard websocket session; required; default none.
- identity: membership is by the queue object's hash/equality identity. The registry does not derive identity from the websocket object, client address, workflow id, browser tab id, or any queue contents.
- ownership: callers are responsible for pairing the queue with exactly one outbound websocket loop and unregistering it during websocket cleanup.
- contents: the queue may be empty or already contain fragments at registration time; registration does not inspect, drain, or seed it.
- initial snapshot: registration happens before the session sends the direct first shell snapshot, so a concurrent broadcast after registration can enqueue to the queue before the send loop task begins consuming it.

#### Algorithm

- Reads: the current process-local `CLIENTS` set.
- Inserts: the supplied queue into `CLIENTS` exactly once as set membership; an already-present queue leaves the set unchanged.
- Returns: `None` immediately after the set operation completes; no acknowledgement value, queue snapshot, or client count is produced.

#### Effects

- Writes: inserts the supplied queue into `CLIENTS`.
- Preserves: workflow records, gate maps, sidecar connections, logs, queued fragments already present on any queue, and websocket transport state.
- Does not: render HTML, send websocket frames, validate queue ownership, create queues, or persist client membership outside process memory.
- Bottoms out: the layer only calls the built-in set membership operation for `CLIENTS`; it calls no other first-party groom symbol.

### method-unregister-dashboard-client

- sig: `remove_client(queue: asyncio.Queue) -> None`
- abstract: false
- raises: none intentionally raised by the registry operation.
- code: groom/groom/state.py::remove_client

Removes one websocket outbound queue from the process-local client set. Removing an absent queue is a no-op.

#### Inputs

- queue: an `asyncio.Queue` object previously created for one dashboard websocket session; required; default none.
- identity: removal is by the queue object's hash/equality identity, the same identity used during registration. The registry does not derive removal identity from the websocket object, client address, workflow id, browser tab id, or queue contents.
- absent queue: a queue that is not currently in `CLIENTS` is accepted and leaves the set unchanged.
- cleanup scope: unregistering affects only future broadcast membership; queue draining, task cancellation, and websocket close behavior remain owned by the dashboard websocket session and send loop.

#### Algorithm

- Reads: the current process-local `CLIENTS` set.
- Removes: discards the supplied queue from `CLIENTS` when present; the operation does not raise for an absent queue.
- Returns: `None` immediately after the set operation completes; no acknowledgement value, queue snapshot, or client count is produced.

#### Effects

- Writes: removes at most the supplied queue object from `CLIENTS`.
- Broadcast consequence: future calls to [broadcast dashboard fragment](#method-broadcast-dashboard-fragment) no longer target this queue after successful removal; any broadcast snapshot taken before removal may still contain it.
- Preserves: queued fragments already held by that queue object, all other registered queues, workflow records, gate maps, sidecar connections, logs, and websocket transport state.
- Does not: close the websocket, cancel the outbound loop, place a sentinel item, drain queued fragments, render HTML, send websocket frames, validate queue ownership, or persist client membership outside process memory.
- Bottoms out: the layer only calls the built-in set discard operation for `CLIENTS`; it calls no other first-party groom symbol.

### method-broadcast-dashboard-fragment

- sig: `async broadcast(html_fragment: str) -> None`
- abstract: false
- raises: propagates exceptions from a queued client's `put` operation; no domain-specific error value is returned.
- code: groom/groom/state.py::broadcast

Enqueues one already-rendered HTML fragment for every dashboard websocket queue that is registered at the start of the broadcast pass.

#### Inputs

- html_fragment: required string; default none; may be a full shell update, an out-of-band partial, a script fragment, or concatenated fragments.
- client membership: read from the process-local `CLIENTS` set exactly once per broadcast pass by copying it into a list before queue writes begin.
- target type: every snapshot member is treated as an awaitable queue with a `put` method accepting the supplied string.
- backpressure: with the session-created unbounded queues, the `put` normally completes without waiting for browser delivery; the method still awaits each `put` and would inherit blocking behavior from any nonstandard queue-like member.

#### Effects

- Reads: copies the current `CLIENTS` set into a list before enqueueing, so clients that connect or disconnect after that snapshot do not change the target set for this pass.
- Enqueues: awaits `queue.put(html_fragment)` once for each queue in the snapshot, passing the exact string object supplied by the caller without rendering, wrapping, filtering, or cloning it.
- Emits: no return value; completion means every queue in the snapshot accepted the fragment.
- Failure: if a queue put raises or cancellation interrupts the coroutine, the exception propagates to the caller after any earlier queues in the iteration may already have accepted the fragment; the method does not roll back those enqueues.
- Empty set: when no dashboard clients are registered, the copied target list is empty and the method completes without enqueueing or raising a no-clients condition.
- Does not: mutate `CLIENTS`, create or remove clients, inspect workflow state, render dashboard fragments, append notification scripts, call `task_done`, send websocket frames directly, contact sidecar sockets, write logs, retry failed clients, or persist broadcast data outside process memory.
- Bottoms out: the layer only calls each queue's awaitable `put` method; it calls no other first-party groom symbol.

## Algorithms

### algorithm-register-one-dashboard-client

- step: Receive the outbound queue allocated for an accepted dashboard websocket session.
- step: Add that exact queue object to the process-local client set.
- step: Return without emitting a count, snapshot, websocket frame, or acknowledgement.

### algorithm-unregister-one-dashboard-client

- step: Receive the outbound queue associated with a dashboard websocket session cleanup path.
- step: Discard that exact queue object from the process-local client set, tolerating an already-absent queue.
- step: Return without closing the websocket, cancelling tasks, draining the queue, or emitting a count.

### algorithm-broadcast-one-dashboard-fragment

- step: Receive one already-rendered HTML fragment string from a caller that owns rendering and payload composition.
- step: Copy the current client set into a list to freeze the target queues for this broadcast pass.
- step: For each queue in that target list, await one `put` of the exact supplied fragment string.
- step: Complete after the last target queue accepts the fragment, or propagate the first queue/cancellation exception encountered after any earlier successful puts.
- step: Leave websocket text-frame delivery to each queue's owning [dashboard websocket send loop](dashboard-websocket-send-loop.md).

## Failure Semantics

- Registering and unregistering intentionally return no failure result; ordinary Python failures from invalid or unhashable queue-like objects are not converted into domain errors.
- Broadcast cancellation or queue-put failure can produce partial delivery to the target list; already-enqueued fragments remain queued, later target queues may not receive the fragment, and the client set itself remains unchanged.
- A stale queue that remains registered until session cleanup still receives future enqueues; actual websocket send failure is handled by the owning dashboard websocket session rather than by the queue set.
