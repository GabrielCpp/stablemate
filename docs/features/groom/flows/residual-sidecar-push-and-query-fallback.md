---
type: flow
slug: residual-sidecar-push-and-query-fallback
title: Residual sidecar push and query fallback
---
# Residual sidecar push and query fallback

This journey covers Groom's non-primary sidecar paths: the one-shot
[`groom-sidecar --query`](../groom-sidecar.md#groom-sidecar-root) pull used by
startup/manual discovery, the residual `--exit-code` and HTTP progress/blocked
push producers that reach the [groom server](../http/groom.md) push endpoints,
and the host fallback paths that preserve dashboard behavior when a running
sidecar cannot answer. The shared producer is the [sidecar residual HTTP push
helper](../concepts/sidecar-residual-http-push-helper.md), discovery prefers the
[host-to-container sidecar query](../concepts/host-to-container-sidecar-query.md)
before [volume reconstruction](../concepts/workflow-state.md#transition-volume-reconstruction),
and file/diff endpoints prefer live sidecar RPC before the workspace-volume
fallback readers.

- start: the host `groom` process is running or starting with access to Docker;
  one or more workhorse workflow containers may be running, stopped, legacy, or
  already connected over the primary [sidecar live session](../flows/sidecar-live-session-sync.md);
  and the sidecar process may be invoked in one-shot `--query` or `--exit-code`
  mode by Docker discovery or the workflow container entrypoint.
- code: groom/groom/cli.py::sidecar_main
- code: groom/groom/docker_io.py::sidecar_query
- code: groom/groom/discovery.py::_resolve_container
- code: groom/groom/discovery.py::_resolve_via_volumes
- code: groom/groom/sidecar.py::snapshot
- code: groom/groom/sidecar.py::_push
- code: groom/groom/sidecar.py::push_progress
- code: groom/groom/sidecar.py::push_blocked
- code: groom/groom/sidecar.py::push_exited
- code: groom/groom/sidecar.py::_handle_event
- code: groom/groom/app.py::push_progress
- code: groom/groom/app.py::push_blocked
- code: groom/groom/app.py::push_exited
- code: groom/groom/app.py::_sidecar_rpc
- code: groom/groom/app.py::files
- code: groom/groom/app.py::file_content
- code: groom/groom/app.py::diff
- steps:
  1. A startup discovery scan or manual refresh enters the [per-container
     discovery resolver](../concepts/workflow-discovery-scan.md#method-resolve-container)
     for each Docker candidate. The resolver inspects the container, rejects
     candidates without `/workflow`, `/runs`, and `/workspace` mounts, and builds
     the baseline [workflow container](../concepts/workflow-container.md) from
     Docker inspect metadata before applying any sidecar or volume state.
  2. For a running eligible container, the resolver first uses the
     [host-to-container sidecar query](../concepts/host-to-container-sidecar-query.md).
     The host runs `docker exec -u nobody -e HOME=/claude-state <container_id> uv
     run groom-sidecar --query`, captures stdout, accepts only a decoded JSON
     object, and represents Docker failure, non-zero exit, timeout, legacy command
     failure, non-JSON stdout, or non-object JSON as `None`.
  3. Inside the container, [`groom-sidecar root`](../groom-sidecar.md#groom-sidecar-root)
     parses the root flags before importing the sidecar runtime. When `--query`
     is present, query mode wins even if `--exit-code` is also supplied: it calls
     the sidecar snapshot reader, prints exactly one [sidecar snapshot data](../sidecar-snapshot-data.md)
     JSON object to stdout, and returns without starting the live watch/session
     loop or sending an exited notice.
  4. The [sidecar snapshot data](../sidecar-snapshot-data.md) object contains the
     latest current node from run checkpoint data, the terminal marker from run
     metadata, and every awaiting gate found by a workspace scan. Missing or
     malformed source files become empty strings or an empty gate list; a truthy
     terminal marker takes precedence over retained gates for host state.
  5. When the host receives a dictionary snapshot from the query, discovery
     applies the [sidecar query snapshot transition](../concepts/workflow-state.md#transition-sidecar-query-or-discovery-snapshot):
     truthy `current_node` updates the workflow, truthy `terminal` marks it
     finished and suppresses answerable gates, and otherwise each non-empty gate
     path becomes a [gate info](../concepts/gate-info.md) entry that can make the
     workflow blocked.
  6. If the container is stopped, the sidecar query was skipped, or the running
     query returns `None`, the resolver falls back to [volume reconstruction](../concepts/workflow-state.md#transition-volume-reconstruction).
     It reads the latest run directory through the [Docker run-directory reader](../concepts/docker-run-directory-reader.md),
     reads checkpoint and run metadata through the [workspace volume file-content
     reader](../concepts/workspace-volume-file-content-reader.md), and sweeps the
     workspace for awaiting gates through the [workspace-volume awaiting-file
     reader](../concepts/workspace-volume-awaiting-file-reader.md).
  7. Volume reconstruction applies the same visible state rules as discovery
     snapshot application: terminal evidence marks the workflow finished, while
     non-terminal awaiting gate evidence creates gate records and marks the
     workflow blocked. The fallback never starts the workflow container, mutates
     volumes, answers gate files, opens sidecar sockets, or broadcasts dashboard
     updates by itself; callers install the returned workflow record.
  8. Separately, after the workflow process returns, the container entrypoint may
     invoke [`groom-sidecar --exit-code EXIT_CODE`](../groom-sidecar.md#groom-sidecar-root).
     Because `--query` is false and `--exit-code` is present, the CLI calls
     `push_exited(exit_code)` and returns without starting the live watch/session
     loop.
  9. The [sidecar residual HTTP push helper](../concepts/sidecar-residual-http-push-helper.md)
     merges [sidecar identity data](../sidecar-identity-data.md) with the exited
     event payload, serializes a UTF-8 JSON request, and attempts exactly one
     `POST` to `http://{GROOM_HOST}:{GROOM_PORT}/push/exited` with the configured
     one-shot timeout. HTTP-open and response-close failures are swallowed, so the
     sidecar command does not change the workflow process result when Groom is
     unreachable.
  10. The host [receive exited push](../http/groom.md#receive-exited-push)
      invocation normalizes the container id, rejects an empty id with `ok:
      false`, resolves Docker volume metadata when possible, upserts the workflow
      as finished, records a numeric exit code when the payload supplies one,
      clears every open gate for that workflow, broadcasts the dashboard shell,
      and returns `ok: true` after broadcast succeeds.
  11. Residual progress and blocked HTTP producers use the same helper. A legacy
      or test-only event path classifies watched run writes as progress and
      awaiting workspace files as blocked, then calls `push_progress(current_node)`
      or `push_blocked(file_path, question)`. The `await_operator.py` backstop may
      also post the same [blocked push payload](../blocked-push-payload.md)
      directly, making the endpoint idempotent with live sidecar delivery.
  12. The host [receive progress push](../http/groom.md#receive-progress-push)
      endpoint rejects missing container ids without mutation; otherwise it
      ensures volume metadata when possible, upserts the workflow as running,
      applies optional identity and current-node fields, preserves existing gates,
      broadcasts the dashboard shell, and returns `ok: true`.
  13. The host [receive blocked push](../http/groom.md#receive-blocked-push)
      endpoint rejects missing container ids or empty gate paths without mutation;
      otherwise it ensures volume metadata when possible, upserts the workflow as
      blocked, stores or replaces the gate record for the supplied path, renders a
      dashboard shell plus [blocked notification script fragment](../blocked-notification-script-fragment.md),
      broadcasts the combined fragment, and returns `ok: true`.
  14. For dashboard Files and Diff reads, the host uses a separate fallback path:
      [serve workspace file list](../http/groom.md#serve-workspace-file-list),
      [serve workspace file content](../http/groom.md#serve-workspace-file-content),
      and [serve workspace diff](../http/groom.md#serve-workspace-diff) first ask
      the live sidecar data plane through `_sidecar_rpc`. If no connection exists,
      the socket closes, a reconnect supersedes the connection, the RPC times out,
      or the sidecar returns an error result, `_sidecar_rpc` returns `None`.
  15. When `_sidecar_rpc` returns `None`, the file-list endpoint uses the
      [workspace volume file-list reader](../concepts/workspace-volume-file-list-reader.md),
      the file-content endpoint uses the [workspace volume file-content reader](../concepts/workspace-volume-file-content-reader.md)
      with the combined repo/path guarded against traversal, and the diff endpoint
      uses the [workspace volume diff reader](../concepts/workspace-volume-diff-reader.md).
      Missing workflow ids, missing volume metadata, unsafe paths, non-zero
      reader processes, and absent content become empty `200 OK` text responses
      or fallback data rather than endpoint-specific JSON errors.
- end: discovery has a resolved workflow record from either a running-container
  query snapshot or volume reconstruction; residual exited/progress/blocked pushes
  either update and broadcast host workflow state or fail silently at the producer
  when Groom is unreachable; and dashboard file/diff reads either use a live
  sidecar RPC result or return the documented workspace-volume fallback response.
  These paths preserve the primary live websocket session as the steady-state
  channel while keeping legacy, post-exit, startup, and no-socket cases usable.
- verify: groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch,
  groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates,
  groom/tests/test_sidecar.py::test_push_progress_posts_expected_shape,
  groom/tests/test_sidecar.py::test_push_blocked_posts_expected_shape,
  groom/tests/test_sidecar.py::test_push_exited_posts_expected_shape,
  groom/tests/test_sidecar.py::test_push_exited_is_silent_when_groom_is_unreachable,
  groom/tests/test_sidecar.py::test_push_is_silent_when_groom_is_unreachable,
  groom/tests/test_docker_io.py::test_sidecar_query_parses_snapshot_json,
  groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_nonzero_exit,
  groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_non_json_output,
  groom/tests/test_docker_io.py::test_sidecar_query_returns_none_when_docker_missing,
  groom/tests/test_docker_io.py::test_sidecar_query_returns_none_on_timeout,
  groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container,
  groom/tests/test_discovery.py::test_scan_query_terminal_wins_over_gates,
  groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes,
  groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code,
  groom/tests/test_app.py::test_push_exited_rejects_missing_container_id,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors,
  groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path
- screenshot: docs/features/groom/gui/screenshots/residual-sidecar-push-and-query-fallback-files-file-selected.png
- screenshot: docs/features/groom/gui/screenshots/residual-sidecar-push-and-query-fallback-diff-file-selected.png
