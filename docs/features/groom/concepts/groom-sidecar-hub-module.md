---
type: concept
slug: groom-sidecar-hub-module
title: Groom sidecar hub module
---
# Groom sidecar hub module

The Groom sidecar hub module is the host-process side of persistent sidecar sessions. It defines the current [sidecar connection registry](sidecar-connection-registry.md), the per-socket [sidecar connection](sidecar-connection.md) object, and the [sidecar error](sidecar-error.md) failure signal used when host requests over [sidecar live sessions](../sidecar-live-sessions.md) cannot complete. The [websocket-sidecar](../http/groom.md#websocket-sidecar) endpoint owns socket acceptance and incoming [sidecar websocket frame](../sidecar-websocket-frame.md) dispatch; this module owns only the host-side connection state and outbound RPC/reload data plane.

- code: groom/groom/sidecar_hub.py
- verify: groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_rpc_error_result_raises_sidecar_error,
  groom/tests/test_sidecar_hub.py::test_rpc_times_out_when_no_reply,
  groom/tests/test_sidecar_hub.py::test_correlation_ids_increment_per_connection,
  groom/tests/test_sidecar_hub.py::test_resolve_is_ignored_after_timeout,
  groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection,
  groom/tests/test_sidecar_hub.py::test_send_reload_emits_reload_frame
- refs: [sidecar connection registry](sidecar-connection-registry.md), [sidecar connection](sidecar-connection.md), [sidecar error](sidecar-error.md), [sidecar websocket frame](../sidecar-websocket-frame.md), [sidecar live sessions](../sidecar-live-sessions.md), [websocket-sidecar](../http/groom.md#websocket-sidecar)

## Contract

- role: host-side in-memory hub for one groom process' live sidecar websocket sessions.
- process scope: state is module-level and process-local; it is not persisted, shared across workers, reconciled by Docker inspection, or authoritative for workflow existence.
- event-loop scope: connection operations assume the same event loop owns the accepted websocket, pending RPC futures, and registry callbacks.
- transport boundary: writes JSON frames through accepted sidecar websocket senders; incoming websocket receive, frame validation, and endpoint lifecycle cleanup are outside the module.
- data plane: supports host-issued `getTree`, `getFile`, and `getDiff` RPCs by sending correlated `rpc` frames and resolving correlated `rpc_result` frames.
- reload plane: supports host-issued best-effort sidecar reload by sending a no-payload `reload` frame to current connections.
- fallback contract: socket absence, send failure, timeout, sidecar error result, unregister, or reconnect displacement is reported as [sidecar error](sidecar-error.md) or a missing registry entry so callers can use Docker volume fallback paths.
- authority boundary: losing a sidecar connection never deletes a [workflow container](workflow-container.md), removes a gate, answers an operator question, clears workflow state, or decides an HTTP response body by itself.
- external boundary: `asyncio`, protocol typing, ASGI websocket senders, and exception base behavior are standard-library or framework boundaries and are not Groom-owned graph nodes to descend into.

## Public Member Index

### RPC_TIMEOUT

- kind: module constant.
- detail: folded into [sidecar connection default RPC timeout](sidecar-connection.md#field-default-rpc-timeout).
- value: `5.0` seconds.
- meaning: default maximum wait for one host-issued RPC result before the caller receives [sidecar error](sidecar-error.md) and can fall back.

### SidecarError

- kind: exception class.
- detail: [sidecar error](sidecar-error.md).
- responsibility: represent expected sidecar data-plane unavailability or failed sidecar RPC results without treating them as endpoint-specific programmer errors.

### SidecarConnection

- kind: class.
- detail: [sidecar connection](sidecar-connection.md).
- responsibility: bind one normalized container id to one accepted sidecar websocket sender, serialize outbound sends, track pending RPC futures, resolve sidecar replies, fail outstanding RPCs, and emit reload frames.

### CONNECTIONS

- kind: module state.
- detail: [sidecar connection registry](sidecar-connection-registry.md#field-connections).
- responsibility: map normalized container ids to the currently registered sidecar connection object for that id.

### register

- kind: module function.
- detail: [sidecar connection registry register](sidecar-connection-registry.md#method-register).
- responsibility: make a connection current for its container id and fail pending RPCs on any displaced older connection.

### unregister

- kind: module function.
- detail: [sidecar connection registry unregister](sidecar-connection-registry.md#method-unregister).
- responsibility: remove a closing connection only when it is still current for its id, then fail that connection's pending RPCs.

### get

- kind: module function.
- detail: [sidecar connection registry get](sidecar-connection-registry.md#method-get).
- responsibility: return the current connection for exactly the requested container id, or `None` when none is registered.

### connected_ids

- kind: module function.
- detail: [sidecar connection registry connected ids](sidecar-connection-registry.md#method-connected-ids).
- responsibility: return a snapshot list of registry keys that currently have registered sidecar connections.

## Folded Internal Member

- `_Sender`: private structural sender contract requiring async `send_json(data)`; folded into [sidecar connection](sidecar-connection.md)'s transport contract and not a public Groom concept.

## Module Flow

1. The [websocket-sidecar](../http/groom.md#websocket-sidecar) endpoint accepts a sidecar websocket and creates a [sidecar connection](sidecar-connection.md) after a useful `hello` frame identifies the container.
2. The endpoint calls [register](sidecar-connection-registry.md#method-register), which stores the connection as current for that container id and fails any superseded connection's pending RPCs.
3. HTTP file-tree, file-content, diff, and reload handlers look up the current connection through [get](sidecar-connection-registry.md#method-get), while reload can enumerate current targets through [connected ids](sidecar-connection-registry.md#method-connected-ids).
4. A connection sends host-to-sidecar `rpc` frames with connection-local correlation ids and stores one pending future per in-flight request.
5. The endpoint passes incoming `rpc_result` frames to [sidecar connection](sidecar-connection.md#method-resolve), which completes the matching pending RPC with data or [sidecar error](sidecar-error.md).
6. On timeout, send failure, sidecar error result, socket close, or reconnect displacement, pending RPCs fail through [sidecar error](sidecar-error.md) and callers retain their fallback path.
7. On socket cleanup, the endpoint calls [unregister](sidecar-connection-registry.md#method-unregister); late cleanup from an older displaced socket cannot evict a newer current connection.

## Non-Responsibilities

- Does not accept, close, or read websocket connections; the HTTP endpoint owns the socket lifecycle.
- Does not parse or validate incoming frame objects; endpoint code decides which frame fields to pass into connection and registry operations.
- Does not implement sidecar-side RPC handlers; the in-container [Groom sidecar module](groom-sidecar-module.md) answers host RPC requests.
- Does not perform Docker volume fallback reads, repository path safety checks, file tree construction, file content reads, or diff generation.
- Does not mutate workflow state, broadcast dashboard HTML fragments, decide browser notifications, answer gates, or remove workflow records.
