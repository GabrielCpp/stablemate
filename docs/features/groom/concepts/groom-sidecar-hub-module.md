---
type: concept
slug: groom-sidecar-hub-module
title: Groom sidecar hub module
---
# Groom sidecar hub module

The Groom sidecar hub module is the host-process side of persistent sidecar sessions. It defines the current [sidecar connection registry](sidecar-connection-registry.md), the per-socket [sidecar connection](sidecar-connection.md) object, and the [sidecar error](sidecar-error.md) failure signal used when host requests over [sidecar live sessions](../sidecar-live-sessions.md) cannot complete. The [websocket-sidecar](../http/groom.md#websocket-sidecar) endpoint owns socket acceptance and incoming [sidecar websocket frame](../sidecar-websocket-frame.md) dispatch; this module owns only the host-side connection state and outbound RPC/reload data plane. When a sidecar connection is lost, its cleanup affects only that local connection state and pending RPCs; workflow containers, gates, operator answers, workflow state, and HTTP response bodies remain owned by their respective callers and surfaces.

- code: groom/groom/sidecar_hub.py
- tests: groom/tests/test_sidecar_hub.py::test_ask_questions_rides_the_registered_connections_rpc
- tests: groom/tests/test_sidecar_hub.py::test_answer_gate_carries_run_path_and_body
- refs: [sidecar connection registry](sidecar-connection-registry.md), [sidecar connection](sidecar-connection.md), [sidecar error](sidecar-error.md), [sidecar websocket frame](../sidecar-websocket-frame.md), [sidecar live sessions](../sidecar-live-sessions.md), [websocket-sidecar](../http/groom.md#websocket-sidecar)

## Contract

- role: host-side in-memory hub for one groom process' live sidecar websocket sessions.
- process scope: state is module-level and process-local; it is not persisted, shared across workers, reconciled by Docker inspection, or authoritative for workflow existence.
- event-loop scope: connection operations assume the same event loop owns the accepted websocket, pending RPC futures, and registry callbacks.
- transport boundary: writes JSON frames through accepted sidecar websocket senders; incoming websocket receive, frame validation, and endpoint lifecycle cleanup are outside the module.
- data plane: supports host-issued `getTree`, `getFile`, and `getDiff` RPCs by sending correlated `rpc` frames and resolving correlated `rpc_result` frames.
- reload plane: supports host-issued best-effort sidecar reload by sending a no-payload `reload` frame to current connections.
- fallback contract: socket absence, send failure, timeout, sidecar error result, unregister, or reconnect displacement is reported as [sidecar error](sidecar-error.md) or a missing registry entry so callers can use Docker volume fallback paths.
- gate relay: `ask_questions` and `answer_gate` use the same correlated RPC path to relay operator-gate questions and answers to the run's own control socket through the connected sidecar; the run's reply is returned as a dictionary without being reinterpreted.
- gate failure contract: a missing connection, failed RPC, or non-dictionary RPC result raises [sidecar error](sidecar-error.md); the module does not write gate files or decide whether the caller should use a file fallback.
- external boundary: `asyncio`, protocol typing, ASGI websocket senders, and exception base behavior are standard-library or framework boundaries and are not Groom-owned graph nodes to descend into.

## Public Member Index

`SidecarError` represents expected sidecar data-plane unavailability or failed sidecar RPC results rather than endpoint-specific programmer errors. `SidecarConnection` binds one normalized container id to its accepted sidecar websocket sender, serializes outbound sends, tracks pending RPC futures, resolves sidecar replies, fails outstanding RPCs, and emits reload frames. `CONNECTIONS` maps normalized container ids to their currently registered sidecar connection objects.

### RPC_TIMEOUT

- kind: module constant.
- detail: folded into [sidecar connection default RPC timeout](sidecar-connection.md#field-default-rpc-timeout).
- value: `5.0` seconds.
- meaning: default maximum wait for one host-issued RPC result before the caller receives [sidecar error](sidecar-error.md) and can fall back.

### SidecarError

- kind: exception class.
- detail: [sidecar error](sidecar-error.md).

### SidecarConnection

- kind: class.
- detail: [sidecar connection](sidecar-connection.md).

### CONNECTIONS

- kind: module state.
- detail: [sidecar connection registry](sidecar-connection-registry.md#field-connections).

## Folded Internal Member

- `_Sender`: private structural sender contract requiring async `send_json(data)`; folded into [sidecar connection](sidecar-connection.md)'s transport contract and not a public Groom concept.
- `_gate_rpc`: private async helper that looks up a registered connection, performs one RPC, requires a dictionary reply, and raises [sidecar error](sidecar-error.md) for absence or invalid reply; folded into the two public gate relay functions.

## Module Flow

1. The [websocket-sidecar](../http/groom.md#websocket-sidecar) endpoint accepts a sidecar websocket and creates a [sidecar connection](sidecar-connection.md) after a useful `hello` frame identifies the container.
2. The endpoint calls [register](sidecar-connection-registry.md#method-register), which stores the connection as current for that container id and fails any superseded connection's pending RPCs.
3. HTTP file-tree, file-content, diff, and reload handlers look up the current connection through [get](sidecar-connection-registry.md#method-get), while reload can enumerate current targets through [connected ids](sidecar-connection-registry.md#method-connected-ids).
4. A connection sends host-to-sidecar `rpc` frames with connection-local correlation ids and stores one pending future per in-flight request.
5. The endpoint passes incoming `rpc_result` frames to [sidecar connection](sidecar-connection.md#method-resolve), which completes the matching pending RPC with data or [sidecar error](sidecar-error.md).
6. On timeout, send failure, sidecar error result, socket close, or reconnect displacement, pending RPCs fail through [sidecar error](sidecar-error.md) and callers retain their fallback path.
7. On socket cleanup, the endpoint calls [unregister](sidecar-connection-registry.md#method-unregister); late cleanup from an older displaced socket cannot evict a newer current connection.
8. Gate callers invoke [ask questions](#method-ask-questions) or [answer gate](#method-answer-gate); each delegates to the shared gate RPC helper with `getQuestions` or `answerGate` and returns the run control socket's dictionary reply unchanged.

## Methods

### method-register

- sig: `register(conn: SidecarConnection) -> None`
- abstract: false
- raises: none intentionally.
- verify: json_path(path="exception.type", absent=true)
- code: groom/groom/sidecar_hub.py::register
- detail: [sidecar register documentation scope](sidecar-register-documentation-scope.md).

### method-unregister

- sig: `unregister(conn: SidecarConnection) -> None`
- abstract: false
- raises: none intentionally.
- verify: json_path(path="exception.type", absent=true)
- code: groom/groom/sidecar_hub.py::unregister
- detail: [sidecar unregister documentation scope](sidecar-unregister-documentation-scope.md).

### method-get

- sig: `get(container_id: str) -> SidecarConnection | None`
- abstract: false
- raises: none intentionally.
- verify: json_path(path="exception.type", absent=true)
- code: groom/groom/sidecar_hub.py::get
- detail: [sidecar get documentation scope](sidecar-get-documentation-scope.md).

### method-connected-ids

- sig: `connected_ids() -> list[str]`
- abstract: false
- raises: none intentionally.
- verify: json_path(path="exception.type", absent=true)
- code: groom/groom/sidecar_hub.py::connected_ids
- detail: [sidecar connected ids documentation scope](sidecar-connected-ids-documentation-scope.md).

### method-ask-questions

- sig: `async ask_questions(container_id: str, run: str = "") -> dict[str, Any]`
- abstract: false
- does: Looks up the current sidecar connection for `container_id` and uses it to send the RPC.
- does: Raises [sidecar error](sidecar-error.md) with `no sidecar connected for <container_id>` when no connection is registered.
- verify: json_path(path="exception.type", equals="SidecarError")
- verify: json_path(path="exception.message", matches="no sidecar connected")
- does: Sends one `getQuestions` RPC with `{run: run}` through the connection's normal correlation, timeout, and cleanup behavior.
- verify: emitted(event="rpc", count=1)
- does: Rejects a successful RPC result that is not a dictionary with [sidecar error](sidecar-error.md), naming the returned value.
- verify: json_path(path="exception.type", equals="SidecarError")
- verify: json_path(path="exception.message", matches="non-dict")
- does: Returns a dictionary reply unchanged.
- verify: persists(subject="rpc_reply")
- does: Does not read gate files, alter workflow state, or interpret the questions.
- verify: unchanged(subject="gate_files")
- verify: unchanged(subject="workflow_state")
- raises: [sidecar error](sidecar-error.md) when no sidecar is registered, the RPC fails, or the reply is not a dictionary.
- code: groom/groom/sidecar_hub.py::ask_questions
- input-container-id: exact registry key for the container's current sidecar connection; this function does not normalize or truncate it.
- input-run: run-directory name under the sidecar's `/runs` mount; an empty string asks the sidecar to use its latest run.
- output: the run control socket's dictionary reply, including its `ok` status and question data, returned unchanged.
- calls: [method-get](sidecar-connection-registry.md#method-get), [method-rpc](sidecar-connection.md#method-rpc), and the folded `_gate_rpc` helper.
- algorithm:
  1. Pass the container id, `getQuestions`, and `{run: run}` to the shared gate RPC helper.
  2. Return the validated dictionary reply.

### method-answer-gate

- sig: `async answer_gate(container_id: str, run: str, path: str, body: str) -> dict[str, Any]`
- abstract: false
- does:
  - Builds `{run: run, path: path, body: body}` without changing any supplied value.
  - Looks up the current sidecar connection and raises [sidecar error](sidecar-error.md) if none is registered.
  - Sends one `answerGate` RPC through the connection's normal correlation, timeout, and cleanup behavior.
  - Rejects a successful RPC result that is not a dictionary with [sidecar error](sidecar-error.md), naming the returned value.
  - Returns the dictionary reply unchanged.
  - Leaves persistence and acceptance decisions with the run's control socket.
- verify: json_path(path="path", absent=false)
- verify: json_path(path="exception.type", equals="SidecarError")
- verify: json_path(path="ok", absent=false)
- verify: json_path(path="exception.type", equals="SidecarError")
- verify: json_path(path="exception.message", matches=".*dict.*")
- verify: unchanged(subject="rpc_result")
- verify: unchanged(subject="workflow_state")
- raises: [sidecar error](sidecar-error.md) when no sidecar is registered, the RPC fails, or the reply is not a dictionary.
- code: groom/groom/sidecar_hub.py::answer_gate
- input-container-id: exact registry key for the container's current sidecar connection; this function does not normalize or truncate it.
- input-run: run-directory name under the sidecar's `/runs` mount.
- input-path: container-absolute gate-file path as known by the run's control socket.
- input-body: operator answer text forwarded without trimming or other interpretation.
- output: the run control socket's dictionary reply, including its `ok` status and path/error data, returned unchanged.
- calls: [method-get](sidecar-connection-registry.md#method-get), [method-rpc](sidecar-connection.md#method-rpc), and the folded `_gate_rpc` helper.
- algorithm:
  1. Build the `answerGate` parameter object from `run`, `path`, and `body`.
  2. Pass the container id, `answerGate`, and that parameter object to the shared gate RPC helper.
  3. Return the validated dictionary reply.

## Non-Responsibilities

- Does not accept, close, or read websocket connections; the HTTP endpoint owns the socket lifecycle.
- Does not parse or validate incoming frame objects; endpoint code decides which frame fields to pass into connection and registry operations.
- Does not implement sidecar-side RPC handlers; the in-container [Groom sidecar module](groom-sidecar-module.md) answers host RPC requests.
- Does not perform Docker volume fallback reads, repository path safety checks, file tree construction, file content reads, or diff generation.
- Does not mutate workflow state, broadcast dashboard HTML fragments, decide browser notifications, answer gates, or remove workflow records.
