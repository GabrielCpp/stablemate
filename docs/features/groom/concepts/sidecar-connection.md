---
type: concept
slug: sidecar-connection
title: Sidecar connection
---
# Sidecar connection

Sidecar connection is the host-side object for one live [workflow container](workflow-container.md) sidecar socket. The [groom server](../http/groom.md#websocket-sidecar) creates it after a useful `hello` [sidecar websocket frame](../sidecar-websocket-frame.md), the [sidecar connection registry](sidecar-connection-registry.md) keeps the current connection per container id, file/diff/reload handlers use it as the data plane for [sidecar live sessions](../sidecar-live-sessions.md), [run-sidecar-websocket-session](../http/groom.md#run-sidecar-websocket-session) resolves returned RPC frames through `resolve`, and [sidecar error](sidecar-error.md) is its soft-failure signal for callers that can fall back.

- code: groom/groom/sidecar_hub.py::SidecarConnection
- verify: groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_rpc_error_result_raises_sidecar_error,
  groom/tests/test_sidecar_hub.py::test_rpc_times_out_when_no_reply,
  groom/tests/test_sidecar_hub.py::test_correlation_ids_increment_per_connection,
  groom/tests/test_sidecar_hub.py::test_resolve_is_ignored_after_timeout,
  groom/tests/test_sidecar_hub.py::test_send_reload_emits_reload_frame

## Contract

- identity: one connection is scoped to one normalized workflow container id.
- transport: the connection writes JSON websocket frames to the accepted sidecar socket; it does not read frames itself.
- sender boundary: the socket only needs to satisfy the service-owned `_Sender` protocol (`groom/groom/sidecar_hub.py::_Sender`): one async `send_json(data)` operation that accepts a JSON-compatible frame and returns after the transport accepts or rejects the send. Receiving frames, accepting the websocket, and disconnect cleanup belong to the `/sidecar` endpoint.
- correlation: RPC ids are monotonically increasing strings scoped to this connection.
- default timeout: host-issued RPC calls wait `5.0` seconds unless the caller supplies a shorter or longer timeout for that call.
- concurrency: sends are serialized so concurrent panel reads and reload requests do not write overlapping frames to the same socket.
- failure: send failures, RPC timeouts, sidecar error results, socket closure, and registry displacement reject pending RPCs as sidecar errors so callers can fall back.
- lifecycle: construction only binds the accepted socket; registration, replacement, unregister cleanup, workflow-state mutation, and dashboard broadcasts are owned by the endpoint and [sidecar connection registry](sidecar-connection-registry.md).
- authority: the connection is a non-authoritative acceleration path for sidecar-local file and diff reads; absence or failure of the socket must not remove the [workflow container](workflow-container.md) or suppress volume-read fallbacks.
- inbound boundary: the connection resolves only `rpc_result` payloads explicitly passed to `resolve`; it does not parse incoming websocket frames, decide which messages are useful, or scope progress and blocked updates.

## Fields

### field-container-id

- type: `str`
- default: none
- required: true
- meaning: normalized workflow container id used as the registry key and visible identity for host-side lookups.

### field-socket

- type: object with async `send_json(data)`
- default: none
- required: true
- protocol: private `_Sender` structural contract from `groom/groom/sidecar_hub.py::_Sender`; folded into this concept rather than modeled as a separate public node.
- meaning: accepted websocket sender used for host-to-sidecar `rpc` and `reload` frames; it conforms to `_Sender` and is otherwise opaque to the connection.

### field-pending

- type: `dict[str, asyncio.Future]`
- default: empty dictionary
- required: false
- meaning: outstanding RPC futures keyed by correlation id; entries are removed on result, timeout, send failure, or connection failure.

### field-counter

- type: `int`
- default: `0`
- required: false
- meaning: per-connection counter incremented before each RPC id is emitted.

### field-send-lock

- type: `asyncio.Lock`
- default: new unlocked lock per connection
- required: false
- meaning: serializes websocket sends performed by this connection.

### field-default-rpc-timeout

- type: `float` seconds
- default: `5.0`
- required: false
- code: groom/groom/sidecar_hub.py::RPC_TIMEOUT
- meaning: default maximum wait for one host-issued RPC result before the caller receives a [sidecar error](sidecar-error.md) and can fall back to volume reads; callers may override this per call.

## Methods

### method-init

- sig: `__init__(container_id: str, socket: _Sender) -> None`
- abstract: false
- raises: none intentionally.
- code: groom/groom/sidecar_hub.py::SidecarConnection.__init__
- input-container-id: normalized workflow container id; the constructor stores it unchanged and does not truncate, validate, or coerce it.
- input-socket: accepted websocket sender implementing async `send_json(data)`; the constructor stores the sender unchanged and does not accept, close, or read from it.
- output: returns `None` after initializing the connection object.
- does:
  - Binds the normalized container id and accepted websocket sender to the connection.
  - Initializes the pending-RPC map empty.
  - Initializes the per-connection correlation counter to `0`.
  - Creates one unlocked send lock for serialized host-to-sidecar frames.
  - Does not register the connection, send a frame, inspect workflow state, or create any pending RPC.
- calls: no groom-owned symbol; bottoms out at field initialization and standard-library lock creation.
- algorithm:
  1. Store the supplied container id.
  2. Store the supplied socket sender.
  3. Create an empty pending-RPC dictionary.
  4. Set the correlation counter to `0`.
  5. Create an unlocked send lock.

### method-next-id

- sig: `_next_id() -> str`
- abstract: false
- raises: none intentionally.
- code: groom/groom/sidecar_hub.py::SidecarConnection._next_id
- verify: groom/tests/test_sidecar_hub.py::test_correlation_ids_increment_per_connection
- does:
  - Advances only this connection's correlation counter from its current integer value to the next integer value.
  - Returns the advanced counter value as a decimal string correlation id; the first id after construction is `"1"`.
  - Leaves the pending-RPC map, socket sender, send lock, and registry state unchanged.
  - Calls no groom-owned symbol and bottoms out at integer increment plus string conversion.
- output: decimal string correlation id scoped to this connection.
- calls: no groom-owned symbol.
- algorithm:
  1. Add one to this connection's current integer counter.
  2. Convert the new counter value to a decimal string.
  3. Return the string.

### method-send

- sig: `async _send(frame: dict[str, Any]) -> None`
- abstract: false
- raises: any exception raised by the underlying websocket sender.
- code: groom/groom/sidecar_hub.py::SidecarConnection._send
- verify: groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_send_reload_emits_reload_frame
- does:
  - Waits for this connection's send lock before writing any frame to the accepted sidecar socket.
  - Sends exactly the supplied JSON-serializable frame unchanged through the connection's socket sender.
  - Releases the send lock when the socket send completes or raises, so concurrent RPC and reload calls cannot write to the socket at the same time.
  - Propagates any socket-send exception unchanged to the caller; `rpc` converts that failure into [sidecar error](sidecar-error.md), while reload remains best-effort for its caller.
  - Calls no groom-owned symbol beyond the socket sender protocol, so this layer bottoms out at the websocket transport boundary.
- input-frame: JSON-serializable [sidecar websocket frame](../sidecar-websocket-frame.md) object supplied by the caller.
- output: returns `None` after the socket sender accepts the frame.
- calls: the stored socket sender's async `send_json(data)` operation.
- boundary: the socket sender protocol is the only external operation; receive-loop dispatch, socket acceptance, disconnect cleanup, and incoming-frame normalization remain endpoint responsibilities.
- algorithm:
  1. Wait for exclusive ownership of the connection's send lock.
  2. Pass the supplied frame unchanged to the socket sender.
  3. Release the send lock after the sender returns or raises.
  4. Return `None` when the sender succeeds, or propagate the sender exception when it fails.

### method-rpc

- sig: `async rpc(method: str, params: dict[str, Any], *, timeout: float = RPC_TIMEOUT) -> Any`
- abstract: false
- raises: `SidecarError` when the websocket send fails, the sidecar returns an error result, the connection is displaced or closed while the RPC is pending, or the timeout expires before a result is resolved; propagates caller cancellation while still removing the pending entry.
- code: groom/groom/sidecar_hub.py::SidecarConnection.rpc
- verify: groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_rpc_error_result_raises_sidecar_error,
  groom/tests/test_sidecar_hub.py::test_rpc_times_out_when_no_reply
- input-method: requested sidecar data-plane method name; first-party callers use `getTree`, `getFile`, and `getDiff`.
- input-params: JSON-object parameters sent unchanged in the outgoing `rpc` frame.
- input-timeout: seconds to wait for the matching `rpc_result`; defaults to [field-default-rpc-timeout](#field-default-rpc-timeout).
- does:
  - Allocates the request correlation id through [method-next-id](#method-next-id), so ids are connection-local decimal strings that increase by one per attempted RPC.
  - Stores a pending future under that id before sending the request frame.
  - Sends one `rpc` [sidecar websocket frame](../sidecar-websocket-frame.md) with `type`, `id`, `method`, and `params` through [method-send](#method-send), so the frame shares the connection's serialized host-to-sidecar write path with reload frames.
  - Waits up to the timeout for `resolve` or `fail_all` to complete the future, returns the resolved data unchanged on success, propagates [sidecar error](sidecar-error.md) placed on the future, and converts send failure or timeout to [sidecar error](sidecar-error.md).
  - Always removes the pending future before returning or raising, including send failure before a result wait begins, sidecar-reported failure, registry displacement, socket-close failure, timeout, and caller cancellation.
- output: returns the resolved `rpc_result.data` value unchanged when the sidecar replies with `ok=true` before the timeout.
- cleanup: removes this call's pending future entry after send failure, successful resolution, sidecar-reported failure, registry displacement, socket-close failure, timeout, or caller cancellation; late `resolve` calls for that id therefore have no effect.
- calls: [method-next-id](#method-next-id), [method-send](#method-send), and [sidecar error](sidecar-error.md) for soft-failure reporting.
- algorithm:
  1. Allocate a new connection-local correlation id.
  2. Create a future on the current event loop.
  3. Store the future in the pending-RPC map under the correlation id.
  4. Send one `rpc` frame containing `type: "rpc"`, the correlation id, the requested method, and the params object.
  5. If sending fails, remove the pending entry and raise [sidecar error](sidecar-error.md) with a `send failed:` message.
  6. Wait for the future to complete until the timeout expires.
  7. If the future resolves with data, return that data unchanged.
  8. If the future resolves with [sidecar error](sidecar-error.md), raise that error to the caller.
  9. If waiting times out, raise [sidecar error](sidecar-error.md) naming the method and timeout.
  10. Before leaving the method for any non-send-failure outcome, including caller cancellation, remove the pending entry for the correlation id.

### method-resolve

- sig: `resolve(corr_id: str, *, ok: bool, data: Any = None, error: str = "") -> None`
- abstract: false
- raises: none intentionally; unknown, late, duplicate, or completed correlation ids are ignored.
- code: groom/groom/sidecar_hub.py::SidecarConnection.resolve
- verify: groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_rpc_error_result_raises_sidecar_error,
  groom/tests/test_sidecar_hub.py::test_resolve_is_ignored_after_timeout
- does:
  - Looks up exactly one pending RPC future by the supplied correlation id without creating a future or mutating the pending map.
  - Returns with no effect when the id is unknown, was already removed after timeout, or points at a future that is already complete, so late and duplicate sidecar replies cannot raise or overwrite a caller result.
  - When `ok` is true, completes the waiting future with `data` unchanged; the awaiting `rpc` call returns that value and then removes the pending entry in its own cleanup path.
  - When `ok` is false, completes the waiting future with [sidecar error](sidecar-error.md), using `error` when non-empty and `sidecar reported an error` otherwise; the awaiting `rpc` call observes that exception and then removes the pending entry in its own cleanup path.
- input-corr-id: correlation id string from a sidecar `rpc_result` frame after endpoint normalization.
- input-ok: boolean success value from the sidecar `rpc_result` frame.
- input-data: success payload to deliver unchanged to the waiting `rpc` caller when `ok` is true.
- input-error: error text to wrap in [sidecar error](sidecar-error.md) when `ok` is false.
- output: returns `None` after either completing a future or ignoring the result.
- calls: [sidecar error](sidecar-error.md) only for failed result futures.
- algorithm:
  1. Look up the pending future by correlation id.
  2. Return without effect when the future is absent.
  3. Return without effect when the future is already complete.
  4. If `ok` is true, set the future result to `data` unchanged and stop.
  5. If `ok` is false, set the future exception to [sidecar error](sidecar-error.md), using the supplied error text or `sidecar reported an error` when it is empty.

### method-fail-all

- sig: `fail_all(message: str) -> None`
- abstract: false
- raises: none intentionally.
- code: groom/groom/sidecar_hub.py::SidecarConnection.fail_all
- verify: groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection
- input-message: failure message to deliver through [sidecar error](sidecar-error.md) to every unresolved pending RPC.
- output: returns `None` after all currently pending futures have either been rejected or skipped because they were already complete.
- does:
  - Iterates over the pending-RPC futures that are present when the method starts.
  - Rejects every unresolved pending RPC future with [sidecar error](sidecar-error.md) carrying the supplied message.
  - Leaves already-completed futures' results or exceptions unchanged.
  - Clears the pending map so later `rpc_result` frames for those ids have no effect.
- calls: [sidecar error](sidecar-error.md).
- algorithm:
  1. For each future currently stored in the pending map, check whether it is already complete.
  2. For every incomplete future, set its exception to [sidecar error](sidecar-error.md) with the supplied message.
  3. Clear the pending map.

### method-send-reload

- sig: `async send_reload() -> None`
- abstract: false
- raises: any websocket-send exception from the underlying socket; callers treat a send failure as a dead or unavailable sidecar.
- code: groom/groom/sidecar_hub.py::SidecarConnection.send_reload
- verify: groom/tests/test_sidecar_hub.py::test_send_reload_emits_reload_frame
- output: returns `None` when the reload frame send succeeds.
- does:
  - Sends exactly one `reload` [sidecar websocket frame](../sidecar-websocket-frame.md) through the serialized send path.
  - Propagates socket-send exceptions to the caller so reload can treat a dead socket as unavailable.
  - Performs no wait for restart, acknowledgement, registry cleanup, or workflow-state mutation.
- calls: [method-send](#method-send).
- algorithm:
  1. Build the no-payload reload frame `{type: "reload"}`.
  2. Send it through [method-send](#method-send).
  3. Return when the send completes.
