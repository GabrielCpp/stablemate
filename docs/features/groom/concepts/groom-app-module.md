---
type: concept
slug: groom-app-module
title: Groom app module
---
# Groom app module

The Groom app module is the HTTP and websocket composition point for the [groom server](../http/groom.md): it owns the Litestar route table, loads the static dashboard entry document used by the [groom dashboard](../gui/screens/groom-dashboard.md), connects browser and sidecar transports to the process-local [workflow registry](workflow-registry.md) owned by the [Groom state module](groom-state-module.md), and schedules startup discovery through the [startup background discovery scan](startup-background-discovery-scan.md). Its public route handlers are the code anchors for the server's endpoints and invocations; its private helpers are folded into the module contract through linked helper concepts such as the [dashboard shell broadcaster](dashboard-shell-broadcaster.md), [sidecar RPC helper](sidecar-rpc-helper.md), [push-first volume metadata resolver](push-first-volume-metadata-resolver.md), [sidecar hello applier](sidecar-hello-applier.md), [sidecar progress applier](sidecar-progress-applier.md), and [sidecar blocked applier](sidecar-blocked-applier.md). The module consumes [progress push payload](../progress-push-payload.md), [blocked push payload](../blocked-push-payload.md), [exited push payload](../exited-push-payload.md), [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md), and [sidecar websocket frame](../sidecar-websocket-frame.md) formats while emitting HTML fragments, plain workspace data, JSON status objects, browser websocket frames, and sidecar websocket frames through the server surface.

- code: groom/groom/app.py
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo,
  groom/tests/test_app.py::test_files_endpoint_returns_newline_separated_paths,
  groom/tests/test_app.py::test_refresh_prunes_vanished_containers,
  groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_reload_broadcasts_to_all_connected_sidecars,
  groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate

## Contract

- role: application module for the `groom` web process; it defines the server factory, first-party HTTP handlers, first-party websocket handlers, and the startup discovery hook.
- surface: [groom server](../http/groom.md), whose route table is fixed by [create app](#method-create-app).
- state owner: mutable workflow, client, answer-log, and scanning state live in the [Groom state module](groom-state-module.md), while sidecar-connection state lives in a sibling sidecar module; this module reads and mutates them through documented state, sidecar, discovery, render, Docker, and gate-answering concepts rather than owning separate persistence.
- startup behavior: importing the module resolves package-local paths and preloads the dashboard HTML bytes; constructing the application registers routes and one startup hook; running the application schedules the initial discovery pass without blocking startup completion.
- transport scope: serves browser HTTP, browser websocket, sidecar websocket, and residual sidecar/backstop HTTP pushes; no handler in this module exposes authentication, external OpenAPI schema entries, or durable database writes.
- failure model: endpoint-specific validation returns small success/failure JSON only where documented; unexpected render, Docker, sidecar, websocket, or discovery exceptions are not converted into module-wide error envelopes.
- fallback model: workspace reads prefer a connected sidecar RPC response when one exists, then fall back to Docker-volume reads only for missing or failed sidecar RPCs and only when the selected workflow has a known workspace volume.
- static assets: static asset serving is delegated to the framework router mounted from [field-assets-dir](#field-assets-dir), while first-party dynamic route behavior remains documented under [groom server](../http/groom.md).

## Fields

### field-assets-dir

- type: `pathlib.Path`
- default: package path `groom/groom/assets`
- required: true
- code: groom/groom/app.py::ASSETS_DIR
- meaning: package-local directory mounted by [get static assets](../http/groom.md#get-static-assets) at `/assets` for dashboard CSS and vendored browser libraries.

### field-dashboard-html

- type: `bytes`
- default: contents of package file `groom/groom/templates/dashboard.html` loaded when the module is imported
- required: true
- code: groom/groom/app.py::_DASHBOARD_HTML
- meaning: immutable browser entry document returned by [serve root dashboard html](../http/groom.md#serve-root-dashboard-html) for `GET /`.

### field-question-notify-limit

- type: `int`
- default: `200`
- required: true
- code: groom/groom/app.py::_QUESTION_NOTIFY_LIMIT
- meaning: maximum gate-question prefix included in browser notification script text for blocked-push and sidecar-blocked updates; stored gate question text remains untruncated.

### field-scan-task

- type: `asyncio.Task | None`
- default: `None`
- required: true
- code: groom/groom/app.py::_scan_task
- meaning: strong process-local reference to the startup background discovery task created by [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan), preventing the event loop from retaining only a weak task reference while the scan runs.

## Public Members

### method-create-app

- sig: `create_app() -> Litestar`
- abstract: false
- raises: propagates framework application construction errors and static router setup errors.
- code: groom/groom/app.py::create_app
- verify: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes
- route-table: [groom server](../http/groom.md) with `GET /`, `GET /search`, `GET /repos`, `GET /files/{container_id}`, `GET /file/{container_id}`, `GET /worker/{container_id}`, `GET /diff/{container_id}`, `POST /refresh`, `POST /push/progress`, `POST /push/blocked`, `POST /push/exited`, `WS /ws`, `WS /sidecar`, `POST /reload`, and `/assets/*`.
- startup-hooks: exactly one first-party hook, [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan).
- does:
  - Constructs the Litestar application for the [groom server](../http/groom.md).
  - Registers every first-party route handler and the package-static `/assets` router in a fixed route-handler list.
  - Registers `_spawn_scan` as the only startup hook so initial Docker discovery is scheduled after application startup begins.
  - Does not run discovery, mutate workflow state, open sockets, read Docker, render dynamic shell fragments, or broadcast dashboard updates during factory execution.

### method-index

- sig: `async index() -> Response`
- abstract: false
- raises: no endpoint-specific errors; framework response failures propagate.
- code: groom/groom/app.py::index
- endpoint: [get root dashboard html](../http/groom.md#get-root-dashboard-html)
- invocation: [serve root dashboard html](../http/groom.md#serve-root-dashboard-html)
- does:
  - Returns [field-dashboard-html](#field-dashboard-html) as `text/html` for the dashboard entry page.
  - Leaves all dynamic fleet, gate, file, diff, and websocket state to follow-up HTTP requests and websocket channels.

### method-search

- sig: `async search(q: str = "") -> Response`
- abstract: false
- raises: propagates renderer failures.
- code: groom/groom/app.py::search
- endpoint: [get search fragment](../http/groom.md#get-search-fragment)
- invocation: [serve search fragment](../http/groom.md#serve-search-fragment)
- does:
  - Reads a [workflow registry](workflow-registry.md) snapshot.
  - Renders the [operator inbox](../operator-inbox.md) message-list fragment for query `q` with out-of-band swap markup.
  - Does not mutate workflow state, run discovery, or scope dashboard status counts to the search query.

### method-repos

- sig: `async repos() -> Response`
- abstract: false
- raises: propagates repository-directory reader or renderer failures.
- code: groom/groom/app.py::repos
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo
- endpoint: [get repository menu](../http/groom.md#get-repository-menu)
- invocation: [serve repository menu](../http/groom.md#serve-repository-menu)
- does:
  - Filters the workflow registry snapshot to containers with known workspace volumes.
  - Reads checkout directories for each eligible volume through the [workspace volume repository-directory reader](workspace-volume-repository-directory-reader.md), resolving eligible containers concurrently and skipping volume-less workflows entirely.
  - Renders [repository menu data](../repository-menu-data.md) into repository picker options.

### method-files

- sig: `async files(container_id: str, repo: str = "") -> Response`
- abstract: false
- raises: propagates unexpected sidecar-registry, Docker, or response-construction failures.
- code: groom/groom/app.py::files
- verify: groom/tests/test_app.py::test_files_endpoint_returns_newline_separated_paths,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors
- endpoint: [get workspace file list](../http/groom.md#get-workspace-file-list)
- invocation: [serve workspace file list](../http/groom.md#serve-workspace-file-list)
- does:
  - Requests `getTree` over the [sidecar RPC helper](sidecar-rpc-helper.md) for the selected container and repository.
  - Falls back to the [workspace volume file-list reader](workspace-volume-file-list-reader.md) when the sidecar cannot serve the request and the workflow has a known workspace volume; skips the fallback and returns empty text when the workflow or volume is missing.
  - Returns newline-separated [workspace file list data](../workspace-file-list-data.md), or an empty text body when no file list is available.

### method-file-content

- sig: `async file_content(container_id: str, repo: str = "", path: str = "") -> Response`
- abstract: false
- raises: propagates unexpected sidecar-registry, Docker, or response-construction failures; unsafe fallback paths are converted to an empty text response.
- code: groom/groom/app.py::file_content
- verify: groom/tests/test_app.py::test_file_endpoint_joins_repo_and_path_and_returns_content,
  groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path,
  groom/tests/test_app.py::test_file_content_prefers_sidecar_socket
- endpoint: [get workspace file content](../http/groom.md#get-workspace-file-content)
- invocation: [serve workspace file content](../http/groom.md#serve-workspace-file-content)
- does:
  - Requests `getFile` over the [sidecar RPC helper](sidecar-rpc-helper.md) for the selected repository and path.
  - Falls back to the [workspace volume file-content reader](workspace-volume-file-content-reader.md) with a combined repository-relative path when the sidecar path is unavailable; skips the fallback and returns empty text when the workflow, volume, or relative path is missing.
  - Returns [workspace file content data](../workspace-file-content-data.md) as plain text, or an empty text body when no safe content can be read.

### method-worker-detail

- sig: `async worker_detail(container_id: str) -> Response`
- abstract: false
- raises: propagates worker-detail renderer or response-construction failures.
- code: groom/groom/app.py::worker_detail
- endpoint: [get worker detail](../http/groom.md#get-worker-detail)
- invocation: [serve worker detail](../http/groom.md#serve-worker-detail)
- does:
  - Looks up the selected [workflow container](workflow-container.md) by id in the [workflow registry](workflow-registry.md).
  - Renders the selected worker detail pane through the [worker detail renderer](worker-detail-renderer.md).
  - Does not broadcast shell updates or overwrite typed answer text through live shell pushes.

### method-diff

- sig: `async diff(container_id: str, repo: str = "") -> Response`
- abstract: false
- raises: propagates unexpected sidecar-registry, Docker, or response-construction failures.
- code: groom/groom/app.py::diff
- verify: groom/tests/test_app.py::test_diff_endpoint_passes_repo_through,
  groom/tests/test_app.py::test_diff_prefers_sidecar_socket
- endpoint: [get workspace diff](../http/groom.md#get-workspace-diff)
- invocation: [serve workspace diff](../http/groom.md#serve-workspace-diff)
- does:
  - Requests `getDiff` over the [sidecar RPC helper](sidecar-rpc-helper.md) for the selected repository.
  - Falls back to the [workspace volume diff reader](workspace-volume-diff-reader.md) when the sidecar cannot serve the diff and the workflow has a known workspace volume.
  - Returns [workspace diff data](../workspace-diff-data.md) as plain text for client-side diff rendering.

### method-refresh

- sig: `async refresh() -> dict`
- abstract: false
- raises: propagates pre-scan broadcast, reconciliation, or post-scan broadcast failures after the documented scanning-flag effects.
- code: groom/groom/app.py::refresh
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers,
  groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable
- endpoint: [post refresh](../http/groom.md#post-refresh)
- invocation: [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet)
- does:
  - Sets the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) true and broadcasts the shell before the manual discovery pass.
  - Runs [reconcile workflow fleet](workflow-registry.md#method-reconcile-workflow-fleet).
  - Clears the scanning flag in all reconciliation outcomes, broadcasts the refreshed shell on success, and returns `ok` plus the discovered workflow count.
  - Leaves the scanning flag true if the initial in-progress shell broadcast itself raises before reconciliation starts, because the guarded cleanup region has not been entered.

### method-push-progress

- sig: `async push_progress(data: dict) -> dict`
- abstract: false
- raises: propagates volume metadata lookup, registry upsert, render, or broadcast failures after input validation succeeds.
- code: groom/groom/app.py::push_progress
- endpoint: [post push progress](../http/groom.md#post-push-progress)
- invocation: [receive progress push](../http/groom.md#receive-progress-push)
- does:
  - Consumes [progress push payload](../progress-push-payload.md) and normalizes `container_id` to the first twelve string characters.
  - Rejects empty container ids with `{"ok": false}` and no mutation.
  - Resolves missing Docker volume metadata through the [push-first volume metadata resolver](push-first-volume-metadata-resolver.md), upserts the worker as running, and broadcasts the dashboard shell.

### method-push-blocked

- sig: `async push_blocked(data: dict) -> dict`
- abstract: false
- raises: propagates volume metadata lookup, registry upsert, render, notification rendering, or broadcast failures after input validation succeeds.
- code: groom/groom/app.py::push_blocked
- endpoint: [post push blocked](../http/groom.md#post-push-blocked)
- invocation: [receive blocked push](../http/groom.md#receive-blocked-push)
- does:
  - Consumes [blocked push payload](../blocked-push-payload.md), requiring a non-empty normalized container id and gate file path.
  - Upserts the workflow as blocked and stores one [gate info](gate-info.md) record for the supplied gate path.
  - Broadcasts the shell plus a [blocked notification script fragment](../blocked-notification-script-fragment.md) whose visible notification text truncates the question to [field-question-notify-limit](#field-question-notify-limit).

### method-push-exited

- sig: `async push_exited(data: dict) -> dict`
- abstract: false
- raises: propagates volume metadata lookup, registry upsert, render, or broadcast failures after input validation succeeds.
- code: groom/groom/app.py::push_exited
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code,
  groom/tests/test_app.py::test_push_exited_rejects_missing_container_id
- endpoint: [post push exited](../http/groom.md#post-push-exited)
- invocation: [receive exited push](../http/groom.md#receive-exited-push)
- does:
  - Consumes [exited push payload](../exited-push-payload.md), requiring a non-empty normalized container id.
  - Upserts the workflow as finished, stores a numeric exit code only when the payload value is integer-like, clears all open gates, and broadcasts the dashboard shell.

### method-dashboard-ws

- sig: `async dashboard_ws(socket: WebSocket) -> None`
- abstract: false
- raises: propagates non-disconnect send-loop, receive-loop, render, broadcast, or command-handler exceptions after cleanup.
- code: groom/groom/app.py::dashboard_ws
- endpoint: [websocket dashboard](../http/groom.md#websocket-dashboard)
- invocation: [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session)
- does:
  - Accepts one browser dashboard websocket connection.
  - Registers an outbound queue in the [dashboard client queue set](dashboard-client-queue-set.md), sends an initial shell snapshot, and runs paired send/receive loops.
  - Delegates inbound [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) objects to the [dashboard websocket receive loop](dashboard-websocket-receive-loop.md) and command handler, and unregisters the queue when the websocket session ends.

### method-dashboard-sidecar

- sig: `async dashboard_sidecar(socket: WebSocket) -> None`
- abstract: false
- raises: propagates non-disconnect websocket, state-application, registry, RPC-resolution, or broadcast failures after current-connection cleanup.
- code: groom/groom/app.py::dashboard_sidecar
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate,
  groom/tests/test_app.py::test_apply_hello_running_when_no_gates,
  groom/tests/test_app.py::test_apply_hello_finished_when_terminal,
  groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively,
  groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection
- endpoint: [websocket sidecar](../http/groom.md#websocket-sidecar)
- invocation: [run sidecar websocket session](../http/groom.md#run-sidecar-websocket-session)
- does:
  - Accepts one sidecar websocket connection and waits for a `hello` [sidecar websocket frame](../sidecar-websocket-frame.md) with a non-empty container id before registering a [sidecar connection](sidecar-connection.md).
  - Ignores non-object frames, ignores frames without a usable `hello` identity before registration, applies `hello`, `progress`, and `blocked` frames through sidecar applier concepts, and resolves `rpc_result` frames against pending host-to-sidecar RPC calls.
  - Unregisters the current sidecar connection on disconnect or exit so pending RPC callers fail fast and future data-plane requests can fall back.

### method-reload

- sig: `async reload(container_id: str = "") -> dict`
- abstract: false
- raises: no intentional exception for a missing target or a dead sidecar send; request parsing and unexpected registry errors can propagate.
- code: groom/groom/app.py::reload
- verify: groom/tests/test_app.py::test_reload_broadcasts_to_all_connected_sidecars,
  groom/tests/test_app.py::test_reload_targets_one_container_when_id_given
- endpoint: [post reload](../http/groom.md#post-reload)
- invocation: [reload sidecars](../http/groom.md#reload-sidecars)
- does:
  - Targets the requested connected sidecar id when `container_id` is non-empty, otherwise snapshots all current ids from the [sidecar connection registry](sidecar-connection-registry.md).
  - Sends one reload command to each live target [sidecar connection](sidecar-connection.md) and counts only accepted sends.
  - Returns `{"ok": true, "reloaded": count}` without waiting for container restart or reconnection.

## Folded Internal Members

### method-all-workflows

- sig: `_all_workflows() -> list[WorkflowContainer]`
- abstract: false
- raises: none intentionally raised for an empty or populated registry.
- code: groom/groom/app.py::_all_workflows
- detail: [all workflows snapshot](workflow-registry.md#method-all-workflows-snapshot)

### method-broadcast-shell

- sig: `async _broadcast_shell() -> None`
- abstract: false
- raises: propagates snapshot, render, or client-queue broadcast failures.
- code: groom/groom/app.py::_broadcast_shell
- detail: [dashboard shell broadcaster](dashboard-shell-broadcaster.md)

### method-ensure-volumes

- sig: `async _ensure_volumes(container_id: str) -> None`
- abstract: false
- raises: propagates unexpected Docker inspection, discovery conversion, or registry upsert failures.
- code: groom/groom/app.py::_ensure_volumes
- detail: [push-first volume metadata resolver](push-first-volume-metadata-resolver.md)

### method-sidecar-rpc

- sig: `async _sidecar_rpc(container_id: str, method: str, params: dict) -> dict | None`
- abstract: false
- raises: no intentional exception for absent sidecars or expected sidecar RPC errors.
- code: groom/groom/app.py::_sidecar_rpc
- detail: [sidecar RPC helper](sidecar-rpc-helper.md)

### method-reconcile

- sig: `async _reconcile() -> int`
- abstract: false
- raises: propagates discovery scan, present-id lookup, and registry prune failures.
- code: groom/groom/app.py::_reconcile
- detail: [reconcile workflow fleet](workflow-registry.md#method-reconcile-workflow-fleet)

### method-handle-command

- sig: `async _handle_command(data: dict) -> None`
- abstract: false
- raises: propagates gate-answering, logging, render, or broadcast failures for answer commands.
- code: groom/groom/app.py::_handle_command
- detail: [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md)
- does:
  - Ignores any browser websocket frame whose `cmd` field is not `answer`.
  - Reads `workflow_id`, `file_path`, and `answer` from the frame, supplies the selected workflow's workspace volume when available, and calls the [gate answering layer](gate-answering-layer.md).
  - Records one [answer log entry](../answer-log-entry.md) for every answer attempt.
  - When the answer succeeds and clears the last gate from a blocked workflow, moves the workflow to the running state before broadcasting.
  - Broadcasts a dashboard shell fragment after every answer attempt and appends a [groom answered script fragment](../groom-answered-script-fragment.md) only for successful answers.

### method-send-loop

- sig: `async _send_loop(socket: WebSocket, queue: asyncio.Queue) -> None`
- abstract: false
- raises: propagates websocket send and cancellation exceptions.
- code: groom/groom/app.py::_send_loop
- detail: [dashboard websocket send loop](dashboard-websocket-send-loop.md)

### method-recv-loop

- sig: `async _recv_loop(socket: WebSocket) -> None`
- abstract: false
- raises: propagates websocket receive and command-handler exceptions.
- code: groom/groom/app.py::_recv_loop
- detail: [dashboard websocket receive loop](dashboard-websocket-receive-loop.md)
- does:
  - Repeatedly receives one JSON browser websocket frame and delegates it to [method-handle-command](#method-handle-command).
  - Does not send responses directly; all browser-visible effects are produced by the delegated command handler and dashboard broadcaster.

### method-apply-hello

- sig: `async _apply_hello(container_id: str, data: dict) -> None`
- abstract: false
- raises: propagates volume metadata, registry, render, or broadcast failures.
- code: groom/groom/app.py::_apply_hello
- detail: [sidecar hello applier](sidecar-hello-applier.md)

### method-apply-socket-progress

- sig: `async _apply_socket_progress(container_id: str, data: dict) -> None`
- abstract: false
- raises: propagates registry, render, or broadcast failures.
- code: groom/groom/app.py::_apply_socket_progress
- detail: [sidecar progress applier](sidecar-progress-applier.md)

### method-apply-socket-blocked

- sig: `async _apply_socket_blocked(container_id: str, data: dict) -> None`
- abstract: false
- raises: propagates registry, render, notification-rendering, or broadcast failures.
- code: groom/groom/app.py::_apply_socket_blocked
- detail: [sidecar blocked applier](sidecar-blocked-applier.md)

### method-background-scan

- sig: `async _background_scan() -> None`
- abstract: false
- raises: propagates reconciliation or completion-broadcast failures after the scanning flag is cleared.
- code: groom/groom/app.py::_background_scan
- detail: [startup background discovery scan](startup-background-discovery-scan.md)

### method-spawn-scan

- sig: `async _spawn_scan() -> None`
- abstract: false
- raises: propagates task creation failures.
- code: groom/groom/app.py::_spawn_scan
- detail: [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan)

## Algorithms

### algorithm-application-startup

- step: Importing the module resolves [field-assets-dir](#field-assets-dir), reads [field-dashboard-html](#field-dashboard-html), and leaves mutable state in sibling state modules.
- step: A caller invokes [create app](#method-create-app) to construct the [groom server](../http/groom.md) route table and register the startup hook.
- step: Litestar startup calls [schedule startup discovery scan](../http/groom.md#schedule-startup-discovery-scan), which stores a background task in [field-scan-task](#field-scan-task) and returns before Docker discovery completes.
- step: The background scan reconciles the [workflow registry](workflow-registry.md), clears the [dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md), and broadcasts the [dashboard shell fragment](../dashboard-shell-fragment.md) to connected dashboard clients.

### algorithm-live-update-convergence

- step: Residual push endpoints and sidecar websocket frames normalize or select one workflow container id.
- step: The module ensures volume metadata when the path needs fallback workspace access, then upserts [workflow state](workflow-state.md) and gate records through the [workflow registry](workflow-registry.md).
- step: The module renders current shell fragments through linked renderer concepts and broadcasts them to the [dashboard client queue set](dashboard-client-queue-set.md).
- step: Browser dashboard websockets receive shell fragments as out-of-band HTML; answer submissions return over the same websocket as [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) objects and re-enter the gate-answering path.
