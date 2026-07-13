---
type: concept
slug: sidecar-connection-registry
title: Sidecar connection registry
---
# Sidecar connection registry

Sidecar connection registry is the process-local map of normalized workflow container ids to the current [sidecar connection](sidecar-connection.md) in the [Groom sidecar hub module](groom-sidecar-hub-module.md). The [websocket-sidecar](../http/groom.md#websocket-sidecar) endpoint registers on useful `hello` [sidecar websocket frame](../sidecar-websocket-frame.md) messages and unregisters on socket cleanup; the [sidecar RPC helper](sidecar-rpc-helper.md) and [post-reload endpoint](../http/groom.md#post-reload) look up this registry to use the sidecar websocket data plane while keeping Docker-volume fallbacks available. Displacement and cleanup fail pending RPCs through the [sidecar error](sidecar-error.md) path, but the registry itself never removes workflow records or decides endpoint fallback responses.

- code: groom/groom/sidecar_hub.py::CONNECTIONS
- verify: groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection

## Contract

- scope: one in-memory registry per groom process and event loop; it is not persisted across process restarts.
- key: normalized workflow container id string.
- value: current [sidecar connection](sidecar-connection.md) for that container id.
- normalization owner: callers supply the exact key; the registry does not truncate, coerce, validate, or canonicalize container ids.
- producer: a useful `/sidecar` `hello` frame creates a new host-side sidecar connection and registers it under `str(identity.container_id)[:12]`.
- consumers: the sidecar RPC helper performs one keyed lookup for file tree, file content, and diff reads; the [post-reload endpoint](../http/groom.md#post-reload) either looks up one requested id or snapshots all connected ids before sending reload frames.
- displacement: registering a new connection for an existing id supersedes the prior connection and fails its pending RPCs.
- cleanup: unregister removes only the connection object that is still current for its id, so a late close from a superseded socket cannot evict a newer reconnect.
- failure signal: displaced or closed connections receive pending-RPC failures through [sidecar error](sidecar-error.md); absence is represented by a `None` lookup result rather than an exception.
- ordering: connected-id enumeration snapshots keys in the registry's current insertion order.
- concurrency boundary: the registry performs plain synchronous map operations and owns no lock, background reconciliation, liveness probe, retry loop, or cross-process coordination.
- availability boundary: absence, displacement, or socket close means there is no current data-plane socket for that id; the registry itself does not remove workflow state, close websockets, inspect Docker, broadcast dashboard updates, send reload frames, or decide fallback responses.

## Fields

### field-connections

- type: `dict[str, SidecarConnection]`
- default: empty dictionary
- required: false
- meaning: process-local map from normalized container id to the current live connection object.
- lifecycle: entries are added or replaced by [method-register](#method-register), removed conditionally by [method-unregister](#method-unregister), read by [method-get](#method-get), and snapshotted by [method-connected-ids](#method-connected-ids).
- ownership: shared by all HTTP and websocket handlers in the groom process; no external store, cross-process replication, persistence, or background reconciliation owns this map.

## Methods

### method-register

- sig: `register(conn: SidecarConnection) -> None`
- abstract: false
- raises: none intentionally.
- code: groom/groom/sidecar_hub.py::register
- verify: groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection
- input-conn: [sidecar connection](sidecar-connection.md) object whose `container_id` is already normalized for use as the registry key; the registry stores the same object and does not clone, wrap, validate, or close it.
- output: returns `None` after the registry entry for `conn.container_id` points at `conn`.
- does:
  - Reads the current registry entry keyed by the supplied connection's normalized `container_id`; it does not normalize or validate the id itself.
  - When the current entry is a different [sidecar connection](sidecar-connection.md), calls that connection's [fail-all](sidecar-connection.md#method-fail-all) method with message `superseded by a new sidecar connection` before changing the registry entry, making any waiting RPC observe [sidecar error](sidecar-error.md).
  - When the current entry is absent or is the same connection object, performs no prior-connection failure.
  - Stores `conn` as the current registry value for `conn.container_id`, replacing any previous value for that key.
  - Does not apply the `hello` frame, mutate workflow state, broadcast dashboard fragments, or send a websocket frame; those effects belong to the endpoint after registration succeeds.
- calls: [sidecar connection fail-all](sidecar-connection.md#method-fail-all) only when a different current connection is displaced; otherwise no groom-owned symbol is called.
- algorithm:
  1. Read the map value currently stored under `conn.container_id`.
  2. If the value exists and is not the same object as `conn`, fail all pending RPCs on that older connection with the superseded-connection message.
  3. Store `conn` in the map under `conn.container_id`.
  4. Return `None`.

### method-unregister

- sig: `unregister(conn: SidecarConnection) -> None`
- abstract: false
- raises: none intentionally.
- code: groom/groom/sidecar_hub.py::unregister
- verify: groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection
- input-conn: [sidecar connection](sidecar-connection.md) object whose socket lifecycle is ending or whose caller wants all of that connection's pending RPCs failed.
- output: returns `None` after the supplied connection's pending RPCs have been failed and the registry has removed it only if it was current.
- does:
  - Reads the current registry entry for `conn.container_id` without creating or normalizing a key.
  - When that current entry is exactly the supplied `conn` object, removes the registry key so later lookups report no connected sidecar for that container id.
  - When the key is absent or points at a different [sidecar connection](sidecar-connection.md), leaves the registry unchanged so a late close from a superseded socket cannot evict a newer reconnect.
  - Calls `conn`'s [fail-all](sidecar-connection.md#method-fail-all) method with message `sidecar connection closed` after the registry branch, regardless of whether the registry entry was removed, making any waiting RPC observe [sidecar error](sidecar-error.md).
  - Does not close the websocket transport, clear workflow gates, mutate workflow state, broadcast dashboard updates, or remove any registry entry for another container id.
- calls: [sidecar connection fail-all](sidecar-connection.md#method-fail-all) on the supplied connection in every branch.
- algorithm:
  1. Read the map value currently stored under `conn.container_id`.
  2. If that value is exactly the same object as `conn`, remove the key from the registry.
  3. If that value is absent or is another connection object, leave the registry unchanged.
  4. Fail all pending RPCs on the supplied connection with the closed-connection message.
  5. Return `None`.

### method-get

- sig: `get(container_id: str) -> SidecarConnection | None`
- abstract: false
- raises: none intentionally.
- code: groom/groom/sidecar_hub.py::get
- verify: groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors,
  groom/tests/test_app.py::test_file_content_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_prefers_sidecar_socket
- input-container-id: lookup key supplied by the caller; callers that use truncated Docker ids must truncate before calling this method.
- output-present: returns the currently registered [sidecar connection](sidecar-connection.md) object for exactly the supplied key.
- output-absent: returns `None` when no current connection is stored under exactly the supplied key.
- does:
  - Reads exactly the registry key supplied by the caller; it does not normalize, truncate, or coerce the id.
  - Returns the current registered connection object for that key when present.
  - Returns `None` when the key is absent, including after the current connection was unregistered or when a caller asks for a differently formatted id.
  - Does not fail pending RPCs, create a connection, send a websocket frame, or trigger a fallback itself; callers decide what absence means for their endpoint.
- calls: no groom-owned symbol; bottoms out at the registry map lookup.
- algorithm:
  1. Look up `container_id` in the registry map.
  2. Return the stored connection object when present.
  3. Return `None` when absent.

### method-connected-ids

- sig: `connected_ids() -> list[str]`
- abstract: false
- raises: none intentionally.
- code: groom/groom/sidecar_hub.py::connected_ids
- verify: groom/tests/test_app.py::test_reload_broadcasts_to_all_connected_sidecars,
  groom/tests/test_app.py::test_reload_targets_one_container_when_id_given
- output: new `list[str]` snapshot of the currently registered container-id keys.
- does:
  - Returns a new list containing the registry keys that currently have registered sidecar connections.
  - Preserves the registry's insertion order for the returned snapshot.
  - Does not keep the returned list live; later connects or disconnects do not change a previously returned target list.
  - Does not validate connection liveness or send reload frames; reload performs a fresh [method-get](#method-get) for each target before sending.
- calls: no groom-owned symbol; bottoms out at the registry map's key iteration.
- algorithm:
  1. Iterate the registry map's keys in their current order.
  2. Materialize those keys into a new list.
  3. Return the list.
