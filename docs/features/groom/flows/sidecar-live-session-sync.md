---
type: flow
slug: sidecar-live-session-sync
title: Sidecar live session sync
---
# Sidecar live session sync

This journey covers the as-built live sidecar synchronization path from the
default [`groom-sidecar`](../groom-sidecar.md) mode through the container-side
[sidecar live session runner](../concepts/sidecar-live-session-runner.md), the
host [`WS /sidecar`](../http/groom.md#websocket-sidecar) endpoint, authoritative
`hello` snapshot application, live `progress` and `blocked` deltas, host-issued
sidecar RPCs used by workspace file and diff reads, disconnect fallback to volume
readers, and the [`POST /reload`](../http/groom.md#post-reload) development-loop
exit path. The protocol payload is the [sidecar websocket frame](../sidecar-websocket-frame.md),
the host-side live socket is the [sidecar connection](../concepts/sidecar-connection.md),
and the visible workflow row state is stored as a [workflow container](../concepts/workflow-container.md).

- start: the host [groom server](../http/groom.md) is running and can accept `WS
  /sidecar`; a workflow container has launched `groom-sidecar` without `--query`
  or `--exit-code`; the sidecar process can read its configured workspace and
  runs mounts, even if the host is temporarily unreachable; the process-local
  [workflow registry](../concepts/workflow-registry.md) may be empty, stale,
  hydrated from residual push endpoints, or already carrying a previous sidecar
  connection for the same container id.
- code: groom/groom/cli.py::sidecar_main
- code: groom/groom/sidecar.py::run
- code: groom/groom/sidecar.py::_serve
- code: groom/groom/sidecar.py::_run_session
- code: groom/groom/sidecar.py::_hello_frame
- code: groom/groom/sidecar.py::_classify_event
- code: groom/groom/sidecar.py::_handle_rpc
- code: groom/groom/sidecar_hub.py::SidecarConnection
- code: groom/groom/sidecar_hub.py::register
- code: groom/groom/sidecar_hub.py::unregister
- code: groom/groom/app.py::dashboard_sidecar
- code: groom/groom/app.py::_apply_hello
- code: groom/groom/app.py::_apply_socket_progress
- code: groom/groom/app.py::_apply_socket_blocked
- code: groom/groom/app.py::_sidecar_rpc
- code: groom/groom/app.py::files
- code: groom/groom/app.py::file_content
- code: groom/groom/app.py::diff
- code: groom/groom/app.py::reload
- steps:
  1. The container entrypoint invokes [groom-sidecar root](../groom-sidecar.md#groom-sidecar-root)
     with neither mode flag. The CLI parses successfully, imports the sidecar
     runtime, and selects the default long-running path instead of the one-shot
     query or exited-notice paths.
  2. The [sidecar live session runner](../concepts/sidecar-live-session-runner.md)
     starts the [sidecar serving loop](../concepts/sidecar-serving-loop.md) and
     waits for it. It returns normally only for a zero serving-loop result and
     maps any non-zero result, including the reserved reload result, to the
     process exit status observed by the container entrypoint.
  3. The serving loop builds `ws://{GROOM_HOST}:{GROOM_PORT}/sidecar` and enters
     the websocket connector's retrying connection loop. A temporarily unavailable
     host groom process does not terminate the sidecar process; the connector
     keeps trying until it yields a socket, and each later ordinary socket close
     returns to this same reconnect path.
  4. For each connected socket, [sidecar connected session](../concepts/sidecar-connected-session.md)
     immediately sends one `hello` [sidecar websocket frame](../sidecar-websocket-frame.md)
     before installing watches or reading host frames. The `hello` combines
     [sidecar identity data](../sidecar-identity-data.md) from hostname and repo
     environment values with [sidecar snapshot data](../sidecar-snapshot-data.md)
     read from the latest run checkpoint, latest run metadata, and a workspace
     sweep for awaiting operator gates.
  5. The host [run sidecar websocket session](../http/groom.md#run-sidecar-websocket-session)
     accepts `WS /sidecar`, ignores non-object JSON values, and waits for a useful
     `hello`. A pre-hello `progress`, `blocked`, or `rpc_result` frame has no
     effect because no connection identity exists yet.
  6. On a useful `hello`, the host normalizes `identity.container_id` to the first
     twelve characters, constructs a [sidecar connection](../concepts/sidecar-connection.md),
     and registers it in the [sidecar connection registry](../concepts/sidecar-connection-registry.md).
     If another live connection for that id was already registered, the new one
     supersedes it and the old connection's pending RPC futures fail with a
     sidecar error so waiting HTTP handlers can fall back.
  7. The host applies the `hello` through [sidecar hello applier](../concepts/sidecar-hello-applier.md):
     it resolves Docker volume metadata when possible, updates identity fields,
     preserves the current node unless the snapshot supplies a truthy replacement,
     clears stale gates, rebuilds gates from non-empty `snapshot.gates[].file_path`
     entries, marks the workflow `finished` for a truthy terminal marker,
     otherwise marks it `blocked` when rebuilt gates exist or `running` when none
     exist, and broadcasts a dashboard shell fragment.
  8. After advertising, the sidecar session installs recursive watches below the
     workspace and runs mounts, starts the [sidecar outbound sender](../concepts/sidecar-outbound-sender.md),
     and continues consuming host frames. New watched directories only expand the
     watch set; they do not emit state frames by themselves.
  9. When a watched runs-file write is classified, the sidecar emits a `progress`
     frame carrying the latest current node. The host handles it through
     [sidecar progress applier](../concepts/sidecar-progress-applier.md), upserts
     the connected workflow as `running`, applies non-null current-node values,
     preserves existing gates, and broadcasts the dashboard shell to browser
     websocket clients.
  10. When a watched workspace file is classified as an awaiting gate, the sidecar
      emits a `blocked` frame with workspace-relative `file_path` when possible
      and extracted question text. The host handles it through
      [sidecar blocked applier](../concepts/sidecar-blocked-applier.md), ignores
      empty paths, otherwise upserts the workflow as `blocked`, stores or replaces
      one [gate info](../concepts/gate-info.md), broadcasts the dashboard shell,
      and appends the blocked browser-notification script fragment.
  11. When the dashboard Files or Diff path requests workspace data, the
      corresponding server invocation first uses the live connection instead of
      Docker fallback: [serve workspace file list](../http/groom.md#serve-workspace-file-list)
      sends `getTree`, [serve workspace file content](../http/groom.md#serve-workspace-file-content)
      sends `getFile`, and [serve workspace diff](../http/groom.md#serve-workspace-diff)
      sends `getDiff` through the [sidecar RPC helper](../concepts/sidecar-rpc-helper.md).
      Each request becomes one host-to-sidecar `rpc` frame with a connection-local
      decimal correlation id and method-specific params.
  12. The sidecar session handles each `rpc` frame serially through the sidecar RPC
      dispatcher. `getTree` returns sorted repo-relative file paths, `getFile`
      validates the combined repo/path with the local relative-path guard before
      returning raw text or empty content, and `getDiff` returns unified git diff
      text for the selected checkout or an empty string on diff-read failure.
      Unknown methods and handler exceptions return `rpc_result` with `ok=false`
      instead of terminating the session.
  13. The host endpoint resolves `rpc_result` frames through the registered
      connection. Matching successful ids deliver the raw `data` object to the
      waiting HTTP handler; failed results deliver a [sidecar error](../concepts/sidecar-error.md);
      late, duplicate, unknown, or already-timed-out ids are ignored without
      mutating workflow state or broadcasting.
  14. If a sidecar RPC succeeds, the HTTP handler serializes the returned sidecar
      data directly as the endpoint response: newline-separated [workspace file
      list data](../workspace-file-list-data.md), raw [workspace file content data](../workspace-file-content-data.md),
      or raw [workspace diff data](../workspace-diff-data.md). The handler does
      not consult Docker volumes on the successful sidecar path.
  15. If no connection is registered, the socket send fails, the RPC times out,
      the sidecar replies with an error result, a reconnect supersedes the
      connection, or the socket closes, the RPC helper returns `None`. The file
      and diff invocations then use the already documented workspace-volume
      fallback readers when the workflow has volume metadata, or return an empty
      `200 OK` text response when no fallback data is available.
  16. On an ordinary sidecar websocket disconnect, the host unregisters the
      connection only if it is still current for that container id, fails every
      pending RPC on that closing connection with `sidecar connection closed`, and
      leaves the workflow row, current node, gates, and visible state in the
      registry. The container-side serving loop treats the close as non-terminal
      and reconnects, causing a fresh authoritative `hello` snapshot to resync
      state.
  17. When a developer or compatible client posts to [reload sidecars](../http/groom.md#reload-sidecars),
      the host targets either the supplied `container_id` or a snapshot of all
      currently connected sidecar ids, looks up each connection, and sends a
      best-effort `reload` frame through the connection's serialized send path.
      Missing connections and send failures skip only that target and do not fail
      the HTTP request.
  18. The sidecar session treats an inbound `reload` frame as a control message,
      sends no acknowledgement or RPC result, raises the reload control signal,
      and performs normal session cleanup for watches, file-descriptor readers,
      sender task, and inotify handle.
  19. The serving loop catches the reload signal, closes the current websocket
      best-effort, returns the reserved reload exit code `3`, and stops
      reconnecting. The runner maps that non-zero result to `SystemExit(3)`, which
      lets the container entrypoint recopy edited sidecar code and relaunch the
      default `groom-sidecar` session.
- end: while connected, each useful `hello`, `progress`, and non-empty-path
  `blocked` frame converges the host workflow registry and dashboard shell toward
  the sidecar's observed container state, and file/diff reads prefer the live
  socket data plane. A dropped socket is not authoritative: it fails pending RPCs
  to the documented fallback readers and waits for reconnect rather than deleting
  workflow state. A reload request intentionally terminates only the sidecar
  process with exit code `3`; the workflow process's own status remains outside
  the live session and is reported separately by the `--exit-code` residual path.
- verify: groom/tests/test_sidecar_session.py::test_cli_sidecar_default_runs_session,
  groom/tests/test_sidecar_session.py::test_hello_frame_carries_identity_and_snapshot,
  groom/tests/test_sidecar_session.py::test_run_session_advertises_hello_then_reload_raises,
  groom/tests/test_sidecar_session.py::test_serve_returns_reload_code_when_session_requests_reload,
  groom/tests/test_sidecar_session.py::test_run_maps_reload_code_to_systemexit,
  groom/tests/test_sidecar_session.py::test_classify_event_runs_write_is_progress,
  groom/tests/test_sidecar_session.py::test_classify_event_awaiting_gate_is_blocked,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_tree_replies_ok,
  groom/tests/test_sidecar_session.py::test_handle_rpc_unknown_method_replies_error,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_file_traversal_replies_error,
  groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_rpc_error_result_raises_sidecar_error,
  groom/tests/test_sidecar_hub.py::test_rpc_times_out_when_no_reply,
  groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection,
  groom/tests/test_sidecar_hub.py::test_send_reload_emits_reload_frame,
  groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate,
  groom/tests/test_app.py::test_apply_hello_running_when_no_gates,
  groom/tests/test_app.py::test_apply_hello_finished_when_terminal,
  groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors,
  groom/tests/test_app.py::test_file_content_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_prefers_sidecar_socket,
  groom/tests/test_app.py::test_reload_broadcasts_to_all_connected_sidecars,
  groom/tests/test_app.py::test_reload_targets_one_container_when_id_given
- screenshot: docs/features/groom/gui/screenshots/sidecar-live-session-sync-detail-diff.png
- screenshot: docs/features/groom/gui/screenshots/sidecar-live-session-sync-files-pane.png
- screenshot: docs/features/groom/gui/screenshots/sidecar-live-session-sync-diff-file-selected.png
