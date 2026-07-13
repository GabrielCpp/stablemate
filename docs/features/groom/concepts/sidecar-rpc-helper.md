---
type: concept
slug: sidecar-rpc-helper
title: Sidecar RPC helper
---
# Sidecar RPC helper

Sidecar RPC helper is the app-level adapter that lets HTTP data-plane handlers ask a connected [sidecar connection](sidecar-connection.md) for workspace data without knowing registry or socket failure details. The [groom server](../http/groom.md) file-list, file-content, and diff invocations call it before falling back to Docker volume readers, and it uses the [sidecar connection registry](sidecar-connection-registry.md#method-get) plus the [sidecar connection RPC method](sidecar-connection.md#method-rpc) to exchange [sidecar websocket frame](../sidecar-websocket-frame.md) messages. Successful helper results bridge sidecar `rpc_result.data` objects into [workspace file list data](../workspace-file-list-data.md), [workspace file content data](../workspace-file-content-data.md), and [workspace diff data](../workspace-diff-data.md) endpoint responses; unavailable or failed sockets preserve those endpoints' Docker-volume fallback paths.

- code: groom/groom/app.py::_sidecar_rpc
- verify: groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors,
  groom/tests/test_app.py::test_file_content_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_prefers_sidecar_socket

## Contract

- purpose: perform one best-effort host-to-sidecar data-plane RPC for a workflow container and collapse socket-unavailable outcomes to `None` so the endpoint handler can choose its Docker-volume fallback.
- callers: file-list, file-content, and diff endpoint invocations call this helper before their fallback readers.
- scope: one container id, one method name, and one params object per call.
- method contract: generic pass-through; the helper does not whitelist method names, reinterpret params, coerce return data, or require the selected method to be one of the current first-party `getTree`, `getFile`, or `getDiff` calls.
- first-party method mapping: file-list handlers pass `getTree` with `{repo}` and expect a result object whose `paths` member feeds [workspace file list data](../workspace-file-list-data.md); file-content handlers pass `getFile` with `{repo, path}` and expect `content` for [workspace file content data](../workspace-file-content-data.md); diff handlers pass `getDiff` with `{repo}` and expect `diff` for [workspace diff data](../workspace-diff-data.md).
- transport shape: the helper never serializes frames itself; it delegates to the connection RPC method, which emits a host-to-sidecar `rpc` frame with a connection-local id, the supplied method string, and the supplied params object, then resolves with the matching `rpc_result.data` value.
- availability boundary: a missing connection and an expected sidecar RPC failure both mean "not served by the live socket"; they do not mean the workflow is gone or the endpoint should fail.
- retry boundary: each helper call performs one registry lookup and, when present, one socket RPC attempt; it does not retry, re-read the registry after failure, or attempt a Docker-volume fallback itself.
- result boundary: successful first-party sidecar methods return JSON-compatible result objects, but this helper returns the connection result unchanged and leaves method-specific keys such as `paths`, `content`, and `diff` to the endpoint caller.
- fallback boundary: returning `None` is only a sidecar-unavailable signal to the endpoint; this helper does not determine whether a workflow has a workspace volume, choose the selected repository root, validate file paths, or convert missing fallback content into an HTTP response body.
- timeout owner: connection-level RPC handling owns correlation ids and the default timeout; the helper does not pass a timeout override or run its own cancellation timer.
- state boundary: this helper does not mutate workflow state, register or unregister sidecars, resolve pending RPCs itself, broadcast dashboard updates, inspect Docker, or read workspace volumes.

## Methods

### method-_sidecar_rpc

- sig: `async _sidecar_rpc(container_id: str, method: str, params: dict) -> dict | None`
- abstract: false
- raises: no intentional exception for an absent sidecar connection or a sidecar RPC failure; unexpected exceptions from registry lookup or non-sidecar failure paths can propagate.
- code: groom/groom/app.py::_sidecar_rpc
- verify: groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors,
  groom/tests/test_app.py::test_file_content_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_prefers_sidecar_socket
- input-container-id: already-selected workflow container id used exactly as the [sidecar connection registry](sidecar-connection-registry.md) lookup key; the helper does not normalize, truncate, coerce, or validate it.
- input-method: sidecar data-plane method requested by the caller; first-party callers use `getTree`, `getFile`, and `getDiff`, matching the `rpc.method` field in [sidecar websocket frame](../sidecar-websocket-frame.md), but the helper accepts any string and sends it unchanged.
- input-params: JSON-object payload sent unchanged in the outgoing RPC; current callers pass the selected `repo`, and file-content calls also pass `path`; the helper does not inspect, complete, copy, validate, escape-check, or default this object.
- output-success: when a current [sidecar connection](sidecar-connection.md) exists and its [method-rpc](sidecar-connection.md#method-rpc) completes successfully, returns the RPC result object exactly as delivered by that connection.
- output-unavailable: returns `None` when no sidecar is currently registered for the supplied container id.
- output-failure: catches only [sidecar error](sidecar-error.md) from the connection RPC and returns `None`, preserving the endpoint-specific fallback path; unrelated exceptions from registry access or unexpected connection behavior remain outside the soft-failure contract.
- output-boundary: does not validate that a successful result is a dictionary, does not normalize missing result keys, and does not convert falsey method-specific values to `None`; those interpretations belong to file-list, file-content, and diff invocations.
- does:
  - Reads the current [sidecar connection registry](sidecar-connection-registry.md) once for `container_id` through [method-get](sidecar-connection-registry.md#method-get).
  - Stops immediately with `None` when the registry has no current connection for the supplied id.
  - Sends at most one `rpc` [sidecar websocket frame](../sidecar-websocket-frame.md) through the returned [sidecar connection](sidecar-connection.md) when present, carrying the method and params unchanged and relying on the connection's default RPC timeout.
  - Returns the connection RPC result unchanged on success so endpoint handlers can interpret method-specific keys such as `paths`, `content`, or `diff`.
  - Converts only expected sidecar socket failures reported as [sidecar error](sidecar-error.md) into `None` instead of an endpoint error so callers can use their Docker-volume fallback readers.
  - Does not inspect workflow containers, select fallback volumes, read workspace files, catch path-safety errors from fallback readers, mutate registry entries, broadcast dashboard fragments, or shape HTTP response bodies.
- calls: [method-get](sidecar-connection-registry.md#method-get), [method-rpc](sidecar-connection.md#method-rpc), and [sidecar error](sidecar-error.md) handling.
- algorithm:
  1. Look up the current sidecar connection for the supplied container id.
  2. If no connection exists, return `None`.
  3. Await one connection RPC using the supplied method and params.
  4. If the RPC succeeds, return its result unchanged.
  5. If the RPC raises [sidecar error](sidecar-error.md), return `None`.
