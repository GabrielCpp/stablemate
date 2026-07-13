---
type: format
slug: sidecar-websocket-frame
title: Sidecar websocket frame
---
# Sidecar websocket frame

The sidecar websocket frame is the JSON message format exchanged on the [websocket-sidecar](http/groom.md#websocket-sidecar) endpoint during [sidecar live sessions](sidecar-live-sessions.md). Incoming sidecar-to-groom frames are consumed by `dashboard_sidecar`; [method-_hello_frame](#method-_hello_frame) creates the full-state `hello` frame from [sidecar identity data](sidecar-identity-data.md) and [sidecar snapshot data](sidecar-snapshot-data.md), while the [sidecar connected session](concepts/sidecar-connected-session.md) and [sidecar outbound sender](concepts/sidecar-outbound-sender.md) emit `progress`, `blocked`, and `rpc_result` frames from inotify events and local data-plane RPC handlers. Groom-to-sidecar `rpc` and `reload` frames are emitted through the registered [sidecar connection](concepts/sidecar-connection.md) held by the [sidecar connection registry](concepts/sidecar-connection-registry.md). `hello` and `blocked` variants create or replace [gate info](concepts/gate-info.md) records when they advertise non-empty gate paths, while `rpc_result.data` embeds the sidecar-produced portions of [workspace file list data](workspace-file-list-data.md), [workspace file content data](workspace-file-content-data.md), or [workspace diff data](workspace-diff-data.md).

- file: websocket text frames on `WS /sidecar`; no on-disk file.
- code: groom/groom/app.py::dashboard_sidecar
- code: groom/groom/sidecar.py::_hello_frame
- code: groom/groom/sidecar.py::_classify_event
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate,
  groom/tests/test_app.py::test_apply_hello_running_when_no_gates,
  groom/tests/test_app.py::test_apply_hello_finished_when_terminal,
  groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively,
  groom/tests/test_sidecar_session.py::test_hello_frame_carries_identity_and_snapshot,
  groom/tests/test_sidecar_session.py::test_classify_event_runs_write_is_progress,
  groom/tests/test_sidecar_session.py::test_classify_event_awaiting_gate_is_blocked,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_tree_replies_ok,
  groom/tests/test_sidecar_session.py::test_handle_rpc_unknown_method_replies_error,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_file_traversal_replies_error,
  groom/tests/test_sidecar_session.py::test_run_session_advertises_hello_then_reload_raises,
  groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_rpc_error_result_raises_sidecar_error,
  groom/tests/test_sidecar_hub.py::test_send_reload_emits_reload_frame

## Contract

- media: JSON object serialized as a websocket text frame.
- shape: one top-level object whose `type` discriminator selects all other meaningful keys; the protocol has no version, timestamp, sequence number, auth token, global container id, or standalone acknowledgement envelope.
- discriminator: top-level `type` string selects the variant.
- direction: `hello`, `progress`, `blocked`, and `rpc_result` are sidecar-to-groom frames; `rpc` and `reload` are groom-to-sidecar frames.
- variants: `hello` is a full-state advertise sent immediately on every sidecar connect or reconnect; `progress` is a current-node liveness delta; `blocked` is a single open-gate delta; `rpc` is a host request for sidecar-local file tree, file content, or diff data; `rpc_result` is the sidecar reply to one `rpc`; `reload` asks the sidecar process to exit with the reload code.
- serialization: the sidecar serializes outbound frames with ordinary JSON text and parses inbound host frames from JSON text; the host endpoint accepts decoded websocket JSON values and sends host-originated `rpc` and `reload` frames as JSON objects through the accepted socket.
- message object rule: every first-party frame is a JSON object; the host endpoint explicitly ignores non-object decoded sidecar frames, while the sidecar session defines only object-shaped host frames as valid input after JSON parsing.
- ordering: frames are processed in socket receive order; a useful `hello` must establish the connection before non-hello sidecar-to-groom frames have effects.
- sidecar send order: a connected sidecar sends one `hello` frame before installing watch-driven frame delivery; subsequent `progress` and `blocked` frames are sent in the order they are dequeued from the session's outbound frame queue, while `rpc_result` replies are sent by the host-frame receive loop for the matching `rpc` request.
- host send order: host-originated `rpc` and `reload` frames are sent through the registered sidecar connection's serialized send path, so concurrent panel RPCs and reload requests do not interleave at the websocket send boundary.
- connection scope: the first useful `hello` with a non-empty normalized `identity.container_id` registers one host-side sidecar connection for that container id; later sidecar-to-groom `progress`, `blocked`, and `rpc_result` frames on that socket are scoped to that registered connection, not to any container id carried in the frame.
- reconnect rule: a new useful `hello` for a container id supersedes any prior live sidecar connection for the same id, fails the old connection's pending RPCs, and rebuilds workflow identity, current node, gates, and lifecycle state from the new hello snapshot.
- acknowledgement: no variant has an explicit acknowledgement frame; successful state changes become visible through dashboard shell broadcasts, and RPC completion is represented only by resolving the matching in-process future.
- ignored host receive cases: the groom endpoint ignores non-object top-level JSON values, unknown `type` values, empty hello container ids, and pre-hello non-hello frames without state mutation, RPC resolution, broadcast, or error frame.
- ignored sidecar receive cases: the sidecar ignores inbound host frames whose raw payload is not valid JSON text, and ignores valid object frames whose `type` is neither `rpc` nor `reload`; valid non-object JSON values are outside the host-to-sidecar frame contract.
- nested-shape boundary: nested `identity`, `snapshot`, `snapshot.gates[]`, and RPC `params` values are expected to be objects; first-party producers send objects, and the protocol does not define coercion of non-object nested values into valid sub-shapes.
- rpc failure semantics: failed or unknown RPC handling returns an `rpc_result` with `ok=false` and an `error` string; a host-side `rpc_result` whose id is late, duplicate, or unknown is ignored by the pending-RPC resolver.
- reload failure semantics: a reload request has no success or failure payload because the sidecar raises its reload control exception, closes the session, and exits with the sidecar reload code.

## Fields

### field-type

- type: `str`
- default: absent means no supported action.
- required: true for any supported action
- wire-key: `type`
- meaning: discriminator with supported values `hello`, `progress`, `blocked`, `rpc_result`, `rpc`, and `reload`.
- consumer-use: groom handles `hello`, `rpc_result`, `progress`, and `blocked` on `/sidecar`; the sidecar handles `rpc` and `reload` after parsing host-originated JSON text.

### field-identity

- type: `object`
- default: `{}`
- required: true for a useful `hello`
- meaning: sidecar identity object supplied on every connect or reconnect.
- applies-to: `hello`
- producer: sidecar identity uses the container hostname truncated to 12 characters for `container_id`, `REPO_NAME` or hostname for `name`, `REPO_NAME` for `repo_name`, and `REPO_BRANCH` for `repo_branch`.
- consumer effect: accepted hello frames use this object to register the socket and to update display identity fields on the workflow container.

### field-identity-container-id

- type: string-convertible JSON value
- default: `""`
- required: true for sidecar registration
- meaning: workflow container id; groom normalizes it with `str(value)[:12]` and ignores the hello when the normalized value is empty.
- applies-to: `hello.identity`
- consumer effect: a useful normalized id scopes the registered [sidecar connection](concepts/sidecar-connection.md), the workflow upsert, and any [gate info](concepts/gate-info.md) rebuilt from the hello snapshot.

### field-identity-name

- type: any JSON value accepted by workflow assignment
- default: omitted
- required: false
- meaning: workflow display name; non-null values update the [workflow container](concepts/workflow-container.md).
- applies-to: `hello.identity`

### field-identity-repo-name

- type: any JSON value accepted by workflow assignment
- default: omitted
- required: false
- meaning: repository name shown for the workflow; non-null values update the [workflow container](concepts/workflow-container.md).
- applies-to: `hello.identity`

### field-identity-repo-branch

- type: any JSON value accepted by workflow assignment
- default: omitted
- required: false
- meaning: repository branch shown for the workflow; non-null values update the [workflow container](concepts/workflow-container.md).
- applies-to: `hello.identity`

### field-snapshot

- type: `object`
- default: `{}`
- required: false
- meaning: authoritative reconnect [sidecar snapshot data](sidecar-snapshot-data.md) for the connected workflow's current node, terminal state, and open gates.
- applies-to: `hello`
- producer: sidecar snapshot reads the latest run checkpoint, latest run terminal marker, and every awaiting gate under the workspace before emitting the hello frame.

### field-snapshot-current-node

- type: any JSON value
- default: omitted
- required: false
- meaning: truthy values replace the workflow's current-node display value; falsey or absent values preserve the existing current node.
- applies-to: `hello.snapshot`

### field-snapshot-terminal

- type: truthy/falsy JSON value
- default: falsey
- required: false
- meaning: truthy values mark the [workflow state](concepts/workflow-state.md) as `finished`; otherwise rebuilt gates decide `blocked` versus `running`.
- applies-to: `hello.snapshot`

### field-snapshot-gates

- type: `list[object]`
- default: `[]`
- required: false
- meaning: authoritative gate list for the connected workflow; groom clears stale gates before applying this list.
- applies-to: `hello.snapshot`

### field-snapshot-gates-file-path

- type: string-convertible JSON value
- default: `""`
- required: true for a gate entry to be retained
- meaning: gate file path and dictionary key for a rebuilt [gate info](concepts/gate-info.md) record; empty values are skipped.
- applies-to: `hello.snapshot.gates[]`

### field-snapshot-gates-question

- type: string-convertible JSON value
- default: `""`
- required: false
- meaning: operator question text stored on the rebuilt [gate info](concepts/gate-info.md) record.
- applies-to: `hello.snapshot.gates[]`

### field-current-node

- type: any JSON value
- default: omitted
- required: false
- meaning: current workhorse node value applied to the connected workflow while marking it `running`; omitted or `null` preserves the previous current-node value, while any other value is assigned as supplied.
- applies-to: `progress`
- producer: sidecar progress frames read this value from the latest run checkpoint after a watched file under the runs directory changes.
- consumer effect: accepted progress frames mark the registered workflow `running`, optionally update the current node, and broadcast the dashboard shell; they do not carry gate information or workflow identity.

### field-file-path

- type: string-convertible JSON value
- default: `""`
- required: true for a `blocked` frame to have an effect
- meaning: gate file path and dictionary key for the live blocked update; empty values are ignored.
- applies-to: `blocked`
- producer: sidecar blocked frames use a workspace-relative path when possible, falling back to the observed path string when the file cannot be relativized to the workspace root.
- consumer effect: accepted blocked frames mark the registered workflow `blocked`, create or replace one gate record keyed by this value, broadcast the dashboard shell, and append a blocked-notification script fragment.

### field-question

- type: string-convertible JSON value
- default: `""`
- required: false
- meaning: operator question text stored on the live blocked gate and truncated only for browser-notification preview text.
- applies-to: `blocked`

### field-id

- type: string-convertible JSON value
- default: `""`
- required: true for RPC correlation
- meaning: per-connection correlation id for `rpc_result` replies and host-issued `rpc` requests.
- applies-to: `rpc_result`, `rpc`
- correlation: host-issued `rpc` ids are decimal strings increasing by one per [sidecar connection](concepts/sidecar-connection.md); the sidecar copies the request id unchanged into the reply frame.
- unknown-result rule: host-side `rpc_result` frames whose normalized id does not match a pending request are ignored without raising, broadcasting, or mutating workflow state.

### field-ok

- type: truthy/falsy JSON value
- default: false
- required: false
- meaning: success flag for an RPC result; false resolves the pending RPC with a sidecar error.
- applies-to: `rpc_result`
- consumer-use: host-side resolution applies normal JSON truthiness through `bool(ok)`; only truthy values deliver `data` to the waiting caller.

### field-data

- type: any JSON value
- default: `null`
- required: false
- meaning: successful RPC payload delivered to the waiting host-side caller.
- applies-to: `rpc_result`
- variant shape: for `getTree`, data is an object with `paths` matching [workspace file list data](workspace-file-list-data.md); for `getFile`, data is an object with `content` matching [workspace file content data](workspace-file-content-data.md); for `getDiff`, data is an object with `diff` matching [workspace diff data](workspace-diff-data.md); when `ok` is false this field is absent or ignored by the host-side resolver.

### field-error

- type: string-convertible JSON value
- default: `""`
- required: false
- meaning: RPC failure message delivered to the waiting host-side caller when `ok` is false.
- applies-to: `rpc_result`

### field-method

- type: `"getTree" | "getFile" | "getDiff"`
- default: none
- required: true
- meaning: sidecar data-plane method requested by the groom server.
- applies-to: `rpc`
- consumer effect: unknown method values are not executed; the sidecar returns an `rpc_result` with `ok=false` and an error naming the unknown method.

### field-params

- type: `object`
- default: `{}`
- required: true
- meaning: method-specific parameters; file tree and diff requests use `repo`, file content requests use `repo` plus `path`.
- applies-to: `rpc`
- consumer-use: absent or falsey `params` becomes an empty object for first-party handlers; method handlers read their own keys and default missing values to empty strings.

### field-params-repo

- type: string-convertible JSON value
- default: `""`
- required: false
- meaning: workspace-relative repository directory selected for `getTree`, `getFile`, or `getDiff`; empty string means the workspace root for tree/file reads and the first discovered repository for diff reads.
- applies-to: `rpc.params` for `getTree`, `getFile`, and `getDiff`

### field-params-path

- type: string-convertible JSON value
- default: `""`
- required: true for useful `getFile`
- meaning: repository-relative file path requested by a file-content RPC; empty values return empty content, and absolute paths, empty path segments, or `..` traversal segments produce an error `rpc_result`.
- applies-to: `rpc.params` for `getFile`

### field-data-paths

- type: `list[str]`
- default: `[]`
- required: true for successful `getTree`
- meaning: sorted repository-relative file paths for the requested checkout, with skipped vendor, VCS, bytecode-cache, and virtual-environment directories omitted; a missing or unavailable repository returns an empty list.
- applies-to: `rpc_result.data` for `getTree`

### field-data-content

- type: `str`
- default: `""`
- required: true for successful `getFile`
- meaning: text content of the requested workspace file decoded with replacement for invalid characters; missing or unreadable files return an empty string.
- applies-to: `rpc_result.data` for `getFile`

### field-data-diff

- type: `str`
- default: `""`
- required: true for successful `getDiff`
- meaning: unified working-tree-versus-HEAD diff for the requested or default repository; no repository, subprocess failure, timeout, or non-zero diff command status returns an empty string.
- applies-to: `rpc_result.data` for `getDiff`

### field-reload-payload

- type: no payload fields beyond `type`
- default: not applicable
- required: false
- meaning: `reload` frames contain no id, params, data, or acknowledgement fields; the frame itself is the complete command.
- applies-to: `reload`
- consumer effect: the sidecar exits the current websocket session with its reload control path so the container entrypoint can recopy edited source and relaunch the sidecar.

## Methods

### method-_hello_frame

- sig: `_hello_frame() -> dict`
- abstract: false
- raises: none intentionally raised by the wrapper itself; exceptions outside the delegated [sidecar identity data](sidecar-identity-data.md) or [sidecar snapshot](concepts/sidecar-snapshot.md) contracts can propagate to the caller.
- code: groom/groom/sidecar.py::_hello_frame
- verify: groom/tests/test_sidecar_session.py::test_hello_frame_carries_identity_and_snapshot
- input: no call arguments; uses the sidecar process's current hostname, repository environment, runs mount, and workspace mount through delegated readers.
- output: one first-party `hello` [sidecar websocket frame](sidecar-websocket-frame.md) object with exactly the top-level producer keys `type`, `identity`, and `snapshot`.
- frame type: the returned frame always sets top-level `type` to the literal string `hello`.
- identity: the returned frame embeds a fresh [sidecar identity data](sidecar-identity-data.md) object under top-level `identity` for container id, display name, repository name, and repository branch.
- snapshot: the returned frame embeds a fresh [sidecar snapshot data](sidecar-snapshot-data.md) object under top-level `snapshot` for current node, terminal state, and open gates.
- freshness: both delegated values are evaluated for this call; the helper does not cache identity or snapshot data across reconnects.
- effects: performs only the delegated local reads needed by identity and snapshot production; does not serialize JSON, send on a websocket, open or close a socket, install inotify watches, register host-side connections, perform HTTP pushes, mutate workflow state, write files, or decide host workflow state.
- calls: [Sidecar identity data](sidecar-identity-data.md) and [method-snapshot](concepts/sidecar-snapshot.md#method-snapshot), in that order.
- algorithm:
1. Build fresh [sidecar identity data](sidecar-identity-data.md).
2. Build fresh [sidecar snapshot data](sidecar-snapshot-data.md) through [method-snapshot](concepts/sidecar-snapshot.md#method-snapshot).
3. Return a JSON-compatible object containing `type: "hello"`, the identity object, and the snapshot object.

### method-_classify_event

- sig: `_classify_event(event, wd_to_path: dict[int, str]) -> dict | None`
- abstract: false
- raises: no intentional exception for unknown watch descriptors, directory events, unreadable workspace files, non-awaiting workspace files, or paths outside configured mounts; unexpected exceptions from the current-node reader or gate text parser can propagate.
- code: groom/groom/sidecar.py::_classify_event
- verify: groom/tests/test_sidecar_session.py::test_classify_event_runs_write_is_progress
- verify: groom/tests/test_sidecar_session.py::test_classify_event_awaiting_gate_is_blocked
- verify: groom/tests/test_sidecar_session.py::test_classify_event_ignores_unknown_wd
- input: one already-received inotify event object with `wd`, `mask`, and `name` attributes, plus the session's watch-descriptor map from watch descriptor integer to watched directory path string.
- output: one outbound sidecar websocket frame object for an interesting file event, or `None` when the event should not emit a frame.
- effects: reads local sidecar filesystem state only when a non-directory workspace event must be classified; it does not send websocket text, enqueue frames, install watches, send residual HTTP pushes, mutate files, mutate host workflow state, or raise reload control signals.
- unknown watch rule: when the event's watch descriptor is absent from `wd_to_path`, returns `None` without inspecting `event.name` or the filesystem.
- directory rule: when the event mask includes the inotify directory flag, returns `None`; directory create and move-in watch installation belongs to the connected session or residual event handler, not to this classifier.
- runs rule: when the event's full path is under the configured runs mount, returns a `progress` frame with `type: "progress"` and `current_node` equal to a fresh [method-_current_node](concepts/sidecar-snapshot.md#method-_current_node) read.
- workspace read rule: non-runs file events are read as text from the observed full path; an `OSError` while reading returns `None`.
- gate status rule: the read file content is classified by [method-status-of](operator-gate-context-file.md#method-status-of), and only the exact awaiting token `AWAITING_OPERATOR` emits a frame.
- blocked frame rule: an awaiting workspace file returns a `blocked` frame with `type: "blocked"`, the gate `file_path`, and the extracted operator `question` from [method-extract-question](operator-gate-context-file.md#method-extract-question).
- path rule: the `blocked.file_path` value is workspace-relative when the full event path can be relativized to the configured workspace mount, otherwise it falls back to the observed full path string.
- freshness: both progress and blocked frame payloads are computed at classification time; the method carries no cursor, debounce state, deduplication cache, timestamp, or previous event memory.
- calls: [method-_current_node](concepts/sidecar-snapshot.md#method-_current_node) for runs events, [method-status-of](operator-gate-context-file.md#method-status-of) for gate lifecycle classification, and [method-extract-question](operator-gate-context-file.md#method-extract-question) for blocked-question extraction.
- algorithm:
  1. Look up the event's watched parent directory from `wd_to_path`; return `None` when it is unknown.
  2. Combine the watched parent directory and event name to obtain the full observed path.
  3. Return `None` for directory events.
  4. If the full observed path is under the runs mount, return a `progress` frame with the latest current node.
  5. Read the full observed file as text; return `None` if it cannot be read.
  6. Classify the file status and return `None` unless it is exactly `AWAITING_OPERATOR`.
  7. Compute the workspace-relative gate path when possible.
  8. Return a `blocked` frame containing the gate path and extracted operator question.

### method-_handle_rpc

- sig: `async _handle_rpc(ws, msg: dict) -> None`
- abstract: false
- raises: no intentional exception for unknown methods or delegated read failures; websocket send failures, JSON serialization failures, cancellation, or non-mapping `msg` values can propagate to the connected session.
- code: groom/groom/sidecar.py::_handle_rpc
- verify: groom/tests/test_sidecar_session.py::test_handle_rpc_get_tree_replies_ok
- verify: groom/tests/test_sidecar_session.py::test_handle_rpc_unknown_method_replies_error
- verify: groom/tests/test_sidecar_session.py::test_handle_rpc_get_file_traversal_replies_error
- input: `ws` is the connected sidecar websocket used for the reply send; `msg` is one decoded host-originated `rpc` [sidecar websocket frame](sidecar-websocket-frame.md) object.
- output: returns `None` after sending exactly one `rpc_result` frame for the request.
- correlation rule: copies `msg.id` unchanged into the reply `id`; missing ids are copied as `null` because the handler does not synthesize, normalize, or reject correlation ids.
- method rule: string-converts `msg.method`, treats an absent method as `""`, and dispatches only the supported method names `getTree`, `getFile`, and `getDiff`.
- params rule: uses `msg.params` when truthy and otherwise uses an empty object; first-party callers send an object, while malformed truthy params are left to the selected handler's own contract.
- unknown method result: an unsupported method sends `{"type":"rpc_result","id":<request id>,"ok":false,"error":"unknown method '<method>'"}` and performs no data-plane read.
- success result: a supported handler that returns data sends `{"type":"rpc_result","id":<request id>,"ok":true,"data":<handler result>}`; `getTree` data follows [workspace file list data](workspace-file-list-data.md), `getFile` data follows [workspace file content data](workspace-file-content-data.md), and `getDiff` data follows [workspace diff data](workspace-diff-data.md).
- failure result: any exception raised by the selected data-plane handler is caught and sent as `{"type":"rpc_result","id":<request id>,"ok":false,"error":str(exception)}` so path-safety failures and local read failures become protocol failures rather than session crashes.
- execution rule: runs the selected synchronous data-plane handler off the event loop before sending the result; while this RPC is awaited, the connected session does not consume the next inbound frame.
- effects: sends one JSON text frame on the websocket; may cause local workspace or runs-volume reads through the selected handler; does not mutate workspace files, mutate host workflow state, register sidecar connections, enqueue inotify frames, perform residual HTTP pushes, close the socket, raise reload control signals, or retry failed sends.
- calls: [workspace file list data](workspace-file-list-data.md) producer for `getTree`, [workspace file content data](workspace-file-content-data.md) producer for `getFile`, and [workspace diff data](workspace-diff-data.md) producer for `getDiff`; JSON serialization and event-loop offloading are standard-library concerns.
- algorithm:
  1. Read the request correlation id, requested method name, and params object from the decoded RPC message.
  2. Look up the method name in the sidecar RPC method table.
  3. If no handler exists, send a failed `rpc_result` with an unknown-method error and stop.
  4. Execute the selected data-plane handler with the params object off the event loop.
  5. If the handler raises, send a failed `rpc_result` whose error text is the exception string and stop.
  6. Send a successful `rpc_result` with the handler's returned data object.
