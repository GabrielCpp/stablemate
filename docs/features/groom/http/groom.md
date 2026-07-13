---
type: server
slug: groom
title: groom server
---
# groom server

- code: groom/groom/app.py::create_app
- openapi: none; every first-party handler is registered with `include_in_schema=False`.

The `groom` server is the Litestar surface used by browser dashboard tabs, workflow-container sidecars, and the `groom-sidecar` development loop. It serves the dashboard shell for the [groom dashboard service](../groom.md), fragments for the [operator inbox](../operator-inbox.md), [worker tree](../worker-tree.md), and file/diff panels, receives residual best-effort pushes described by [sidecar protocol](../sidecar-protocol.md), and owns the persistent sidecar socket described by [sidecar live sessions](../sidecar-live-sessions.md). The route table is fixed by the [Groom app module](../concepts/groom-app-module.md) `create_app` member: one dashboard HTML entry point, five read endpoints for fragments or workspace data, four mutation/push endpoints, two websocket channels, and the vendored static asset mount. Application startup is also fixed by `create_app`: the only startup hook is [schedule startup discovery scan](#schedule-startup-discovery-scan), which schedules the initial discovery scan after the server application is constructed.

The server is single-process and stateful in memory. Startup schedules a background discovery scan without blocking the server bind; live updates are pushed as HTML fragments over the browser websocket and as RPC/messages over sidecar websockets. No route on this surface provides authentication, and the app-level OpenAPI schema intentionally excludes these routes.

## Endpoints

### get-root-dashboard-html

- does:
  - Serves the browser entry document for the [groom dashboard](../gui/screens/groom-dashboard.md).
  - Returns the preloaded dashboard template bytes unchanged for the browser to bootstrap htmx, the websocket extension, vendored assets, and dashboard JavaScript; the template is read into `_DASHBOARD_HTML` when `groom/groom/app.py` is imported, not read from disk for each request.
  - Does not read query parameters, request body, cookies, in-memory workflow state, or Docker state.
  - Does not mutate server state, schedule discovery, or push websocket updates.
- code: groom/groom/app.py::index
- route: `GET /`
- parent: [groom server](#groom-server)
- invocation: [serve-root-dashboard-html](#serve-root-dashboard-html)
- request:
  - method: `GET`
  - path: `/`
  - path variables: none
  - query: none
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/html`
  - body: exact bytes of the packaged dashboard HTML shell from `groom/groom/templates/dashboard.html`.
  - errors: none intentionally emitted by this handler; ordinary framework/static-template import failures are process-level failures, not endpoint error responses.

### get-search-fragment

- does:
  - Reads the current in-memory workflow list from the groom process.
  - Filters the [operator inbox](../operator-inbox.md) message list to workflows that have at least one open gate and, when `q` is non-empty, contain the query in workflow name, repository name, repository branch, workflow type, current node, or gate-file path text.
  - Renders only the inbox/message-list fragment through `render.render_inbox` with `hx-swap-oob`; status-bar fleet counts remain global and are not part of this response, and container ids and gate question text are not search haystacks.
- code: groom/groom/app.py::search
- route: `GET /search`
- parent: [groom server](#groom-server)
- invocation: [serve-search-fragment](#serve-search-fragment)
- request:
  - method: `GET`
  - path: none
  - query: `q` string, optional, default `""`; passed unchanged to inbox rendering, where an empty value means no text filter and a non-empty value becomes a case-insensitive substring filter for inbox rows without trimming, tokenizing, or regex matching.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/html`
  - body: one `<div class="inbox-list" id="inbox-list" hx-swap-oob="true">…</div>` fragment. Rows are sorted blocked first, then running, idle, and finished, with names ascending inside each state. No rows returns the inbox empty state; no rows during discovery returns the loading state only when `q` is empty. Dynamic row text is escaped by the renderer before it enters the fragment.
  - errors: none intentionally emitted by this handler; request parsing failures are framework-level failures, not endpoint-specific responses.

### get-repository-menu

- does:
  - Reads the current in-memory workflow list and keeps only workflows whose workspace volume is known.
  - Lists checkout directories for each eligible workflow concurrently through the [workspace volume repository-directory reader](../concepts/workspace-volume-repository-directory-reader.md).
  - Returns the shared repository picker menu used by the dashboard files and diff panes, with [repository menu data](../repository-menu-data.md) rendered as one selectable [repository menu option](../gui/screens/groom-dashboard.md#repository-menu-option) per `(workflow container, checkout directory)` pair.
  - Excludes this route from the application OpenAPI schema; it is an internal dashboard fragment endpoint rather than a public API contract.
  - Does not accept a repository search query; the dashboard filters returned option rows client-side after the fragment is loaded.
- code: groom/groom/app.py::repos
- route: `GET /repos`
- parent: [groom server](#groom-server)
- invocation: [serve-repository-menu](#serve-repository-menu)
- request:
  - method: `GET`
  - path: `/repos`
  - path variables: none
  - query: none
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/html`
  - body: zero or more repository picker option fragments derived from [repository menu data](../repository-menu-data.md). Each option has `role="option"`, `data-container` set to the workflow container id, `data-repo` set to the volume-relative checkout directory, `data-label` set to the visible `workflow/repo` label, a workflow state dot, an optional workflow type badge, and a visible label. Options are grouped by workflow after sorting workflows by dashboard state order and then workflow name; each workflow's checkout directories are already sorted by checkout discovery. A workflow whose volume contains no checkout contributes one volume-root option labelled with the workflow name only; no eligible workflows returns the non-interactive `No repositories available.` empty-state fragment.
  - errors: none intentionally emitted by this handler; Docker discovery failures for an individual volume are represented as an empty checkout list for that workflow, and request parsing failures are framework-level failures.
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo

### get-workspace-file-list

- does:
  - Serves the [groom dashboard](../gui/screens/groom-dashboard.md) Files panel with the selected checkout's file inventory for one workflow container.
  - Produces [workspace file list data](../workspace-file-list-data.md) for the selected workflow checkout.
  - Prefers the live sidecar data plane from [sidecar live sessions](../sidecar-live-sessions.md): sends `getTree` with the selected `repo` and, when the RPC returns data, joins the returned `paths` array with newline separators.
  - Falls back to the workflow's known workspace volume when the sidecar is absent, times out, closes, or reports an error.
  - Reads the fallback file list through the [workspace volume file-list reader](../concepts/workspace-volume-file-list-reader.md) as repo-relative paths within the selected checkout and returns them sorted by the fallback reader.
  - Returns an empty `text/plain` body when the workflow id is unknown, the workflow has no workspace volume, the fallback Docker reader process exits non-zero, the selected checkout has no retained file names, or neither path can provide file names.
  - Does not mutate workflow state, start discovery, broadcast dashboard updates, read file contents, compute diffs, or validate that `repo` is a git checkout.
- code: groom/groom/app.py::files
- route: `GET /files/{container_id}`
- parent: [groom server](#groom-server)
- invocation: [serve-workspace-file-list](#serve-workspace-file-list)
- request:
  - method: `GET`
  - path: `/files/{container_id}`
  - path variable: `container_id` string, required, no default; workflow container id from dashboard state and sidecar registration state.
  - query: `repo` string, optional, default `""`; volume-relative checkout directory chosen by the repository picker. Empty means the workspace volume root.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/plain`
  - body: zero or more repo-relative file paths joined by `\n`. There is no trailing newline requirement; clients must treat an empty body as "no file tree available".
  - errors: none intentionally emitted by this handler; missing workflow state, missing volume metadata, sidecar RPC failure, and a non-zero Docker fallback process all resolve to `200` with an empty body or fallback data. Request parsing failures, Docker process-launch exceptions, and Docker timeout exceptions are framework-level failures rather than endpoint-specific error bodies.
- verify: groom/tests/test_app.py::test_files_endpoint_returns_newline_separated_paths,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors

### get-workspace-file-content

- does:
  - Serves the [groom dashboard](../gui/screens/groom-dashboard.md) Files panel with the raw text for the selected [file row](../gui/screens/groom-dashboard.md#files-file-row).
  - Produces [workspace file content data](../workspace-file-content-data.md) for the selected workflow checkout path.
  - Prefers the connected sidecar data plane from [sidecar live sessions](../sidecar-live-sessions.md): sends `getFile` with the selected `repo` and `path`, then returns the RPC result's `content` value when the sidecar path succeeds.
  - Falls back to the workflow's known workspace volume when the sidecar is absent, times out, closes, or reports an error.
  - Joins `repo` and `path` into one volume-relative fallback path, preserving an empty `repo` as a root-relative file path and stripping only a leading slash from the combined path.
  - Converts an unknown workflow id, missing workspace volume, empty resolved path, traversal-guard failure, missing file, unreadable file, or falsey returned content into a `200 OK` empty `text/plain` response.
  - Does not mutate workflow state, start discovery, broadcast dashboard updates, render syntax highlighting, compute diffs, list directories, or raise endpoint-specific error responses for unavailable file content.
- code: groom/groom/app.py::file_content
- route: `GET /file/{container_id}`
- parent: [groom server](#groom-server)
- invocation: [serve-workspace-file-content](#serve-workspace-file-content)
- request:
  - method: `GET`
  - path: `/file/{container_id}`
  - path variable: `container_id` string, required, no default; workflow container id from dashboard state and sidecar registration state.
  - query: `repo` string, optional, default `""`; volume-relative checkout directory chosen by the repository picker. Empty means the workspace volume root.
  - query: `path` string, optional, default `""`; repo-relative file path chosen from the file tree. Empty means no file is selected and produces an empty response.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/plain`
  - body: raw file text exactly as returned by the sidecar `content` value or fallback volume reader, or an empty string when no content is available. Clients must treat an empty body as "no file content available" rather than as a transport failure.
  - errors: none intentionally emitted by this handler; missing workflow state, missing volume metadata, sidecar RPC failure, empty path, unsafe path, missing files, and fallback read failures all resolve to `200` with an empty body or fallback data. Request parsing failures are framework-level failures.
- verify: groom/tests/test_app.py::test_file_content_prefers_sidecar_socket,
  groom/tests/test_app.py::test_file_endpoint_joins_repo_and_path_and_returns_content,
  groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path

### get-workspace-diff

- does:
  - Serves the [groom dashboard](../gui/screens/groom-dashboard.md) Diff panel or worker-detail working-tree disclosure with the selected checkout's [workspace diff data](../workspace-diff-data.md).
  - Prefers the connected sidecar data plane from [sidecar live sessions](../sidecar-live-sessions.md): sends `getDiff` with the selected `repo` and, when the RPC returns data, returns the RPC result's `diff` value.
  - Falls back to the workflow's known workspace volume when the sidecar is absent, times out, closes, or reports an error.
  - Runs the fallback diff for the selected checkout through the [workspace volume diff reader](../concepts/workspace-volume-diff-reader.md), passing the `repo` query value unchanged.
  - Returns an empty `text/plain` body when the workflow id is unknown, the workflow has no workspace volume, the sidecar response omits or falseys `diff`, or fallback diff collection returns no text.
  - Does not mutate workflow state, start discovery, broadcast dashboard updates, render diff HTML, list files, read individual files, or validate that `repo` is a git checkout.
- code: groom/groom/app.py::diff
- route: `GET /diff/{container_id}`
- parent: [groom server](#groom-server)
- invocation: [serve-workspace-diff](#serve-workspace-diff)
- request:
  - method: `GET`
  - path: `/diff/{container_id}`
  - path variable: `container_id` string, required, no default; workflow container id from dashboard state and sidecar registration state.
  - query: `repo` string, optional, default `""`; volume-relative checkout directory, with an empty value meaning the fallback reader chooses the first repo it finds.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/plain`
  - body: [workspace diff data](../workspace-diff-data.md), serialized as raw unified git diff text exactly as returned by the sidecar `diff` value or fallback volume reader, or an empty string when no diff is available. Clients must treat an empty body as "no diff available" rather than as a transport failure.
  - errors: none intentionally emitted by this handler; missing workflow state, missing volume metadata, sidecar RPC failure, empty sidecar diff, empty fallback output, and fallback git failures all resolve to `200` with an empty body or fallback data. Request parsing failures are framework-level failures.
- verify: groom/tests/test_app.py::test_diff_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_endpoint_passes_repo_through

### get-worker-detail

- does:
  - Looks up the requested workflow container id in the groom process's in-memory workflow registry, yielding either one [workflow container](../concepts/workflow-container.md) or no worker state.
  - Renders only the selected worker detail pane for the [groom dashboard](../gui/screens/groom-dashboard.md), so live shell broadcasts never overwrite a half-typed answer in the browser.
  - Represents an unknown worker as the detail empty state, a known worker without open gates as a read-only status detail, and a known worker with gates as sorted gate blocks plus one shared working-tree diff disclosure.
  - Delegates all fragment markup decisions to the worker-detail renderer; this route only supplies the optional workflow record and wraps the returned fragment in the HTTP response.
  - Does not mutate workflow state, run discovery, contact Docker, contact sidecars, broadcast websocket updates, answer gate files, compute diffs, or render client-side markdown.
- code: groom/groom/app.py::worker_detail
- route: `GET /worker/{container_id}`
- parent: [groom server](#groom-server)
- invocation: [serve-worker-detail](#serve-worker-detail)
- request:
  - method: `GET`
  - path: `/worker/{container_id}`
  - path variable: `container_id` string, required, no default; exact workflow container id used as the registry lookup key.
  - query: none
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/html`
  - body: one `<div id="detail">…</div>` fragment for replacing the selected worker detail pane. Unknown ids return `Worker not found.`; known ids with no gates return the workflow header and `No open gate` status text; known ids with gates return the workflow header, one gate block per open gate sorted by gate file path, escaped gate question markdown in a `data-md` text node, a websocket answer form for each gate, and one `Working-tree diff` disclosure for the worker.
  - errors: none intentionally emitted by this handler; an unknown workflow id is a `200 OK` empty-state fragment, and request parsing failures are framework-level failures.
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form,
  groom/tests/test_render.py::test_worker_detail_has_one_diff_disclosure,
  groom/tests/test_render.py::test_worker_detail_not_found_and_no_gate_states

### post-refresh

- does:
  - Sets the process-local scanning flag to true, then sends a pre-scan dashboard shell broadcast so connected dashboard tabs can show the discovery spinner before Docker discovery starts.
  - Runs one on-demand reconciliation pass through the same path used by startup discovery only after the pre-scan broadcast succeeds.
  - During the reconciliation attempt, clears the scanning flag in all reconciliation outcomes.
  - On a successful reconciliation pass, sends a post-scan dashboard shell broadcast with the refreshed fleet state, then returns the number of workflows discovered by the scan.
  - Does not serialize concurrent refresh requests; overlapping requests share the same process-local scanning flag and workflow registry.
- code: groom/groom/app.py::refresh
- route: `POST /refresh`
- parent: [groom server](#groom-server)
- invocation: [refresh-workflow-fleet](#refresh-workflow-fleet)
- request:
  - method: `POST`
  - path: `/refresh`
  - path variables: none
  - headers: none required by the handler.
  - query: none
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: object with `ok: true` and `count`, the number of workflows found by the reconciliation scan before stale-workflow pruning is considered.
  - field: `ok`; type boolean; required; default none; always `true` on the handler's successful return path.
  - field: `count`; type integer; required; default none; number of workflows returned by discovery before pruning, not the final registry size.
  - errors: no endpoint-specific error body is produced; a pre-scan broadcast failure propagates before reconciliation starts and leaves the scanning flag true, a reconciliation failure clears the scanning flag and skips the post-scan broadcast, and a post-scan broadcast failure propagates after the scanning flag is already false.
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers,
  groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable

### post-push-progress

- does:
  - Receives a best-effort [progress push payload](../progress-push-payload.md) from the container-side sidecar or backstop path described by [sidecar protocol](../sidecar-protocol.md).
  - Normalizes the payload `container_id` to a string and truncates it to the first 12 characters.
  - Rejects an empty normalized container id with `{"ok": false}` and no state mutation or broadcast.
  - Ensures Docker volume metadata has been resolved for the workflow through the [push-first volume metadata resolver](../concepts/push-first-volume-metadata-resolver.md) when possible before updating the visible fleet row.
  - Upserts the workflow as `RUNNING`, applying non-null identity and current-node fields from the payload while preserving fields the payload omits.
  - Broadcasts the dashboard shell after a successful upsert and returns `{"ok": true}`.
- code: groom/groom/app.py::push_progress
- route: `POST /push/progress`
- parent: [groom server](#groom-server)
- invocation: [receive-progress-push](#receive-progress-push)
- request:
  - method: `POST`
  - path: `/push/progress`
  - path variables: none
  - headers: none required by the handler.
  - query: none
  - body: JSON object matching [progress push payload](../progress-push-payload.md).
  - field: `container_id`; type string-convertible value; required for success; default none; normalized to `str(value)[:12]`.
  - field: `name`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the workflow display name.
  - field: `repo_name`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the repository name shown for the worker.
  - field: `repo_branch`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the repository branch shown for the worker.
  - field: `current_node`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the worker's current workflow node.
- response:
  - status: `200` when the handler returns normally.
  - media: `application/json`
  - body: `{"ok": true}` when the normalized container id is non-empty; `{"ok": false}` when it is empty.
  - errors: no endpoint-specific error body is produced; Docker metadata lookup, render, or broadcast failures propagate as framework errors.

### post-push-blocked

- does:
  - Receives a best-effort [blocked push payload](../blocked-push-payload.md) from the workflow container sidecar or the await-operator backstop path described by [sidecar protocol](../sidecar-protocol.md).
  - Normalizes the payload `container_id` to a string and truncates it to the first 12 characters.
  - Normalizes `file_path` to a string and treats an empty value as invalid.
  - Rejects a missing normalized container id or missing gate file path with `{"ok": false}` and no state mutation, Docker metadata lookup, dashboard broadcast, or browser notification.
  - Ensures Docker volume metadata has been resolved for the workflow when possible before updating the visible fleet row.
  - Upserts the workflow as `BLOCKED`, applying non-null identity fields from the payload while preserving fields the payload omits.
  - Stores one open [gate info](../concepts/gate-info.md) record keyed by the normalized gate file path, with `workflow_id` equal to the normalized container id, `file_path` equal to the payload path, `question` equal to the string-normalized payload question or `""`, and status left at the gate model default `AWAITING_OPERATOR`.
  - Broadcasts an out-of-band dashboard shell update plus a [blocked notification script fragment](../blocked-notification-script-fragment.md) whose message is the workflow display name, a colon separator, and the first 200 characters of the gate question.
- code: groom/groom/app.py::push_blocked
- route: `POST /push/blocked`
- parent: [groom server](#groom-server)
- invocation: [receive-blocked-push](#receive-blocked-push)
- request:
  - method: `POST`
  - path: `/push/blocked`
  - path variables: none
  - headers: none required by the handler.
  - query: none
  - body: JSON object matching [blocked push payload](../blocked-push-payload.md).
  - field: `container_id`; type string-convertible value; required for success; default none; normalized to `str(value)[:12]`.
  - field: `file_path`; type string-convertible value; required for success; default none; normalized to `str(value)` and used as the gate key.
  - field: `question`; type string-convertible value; optional; default `""`; normalized to `str(value)` and stored as the gate question, then truncated to 200 characters only for the notification text.
  - field: `name`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the workflow display name.
  - field: `repo_name`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the repository name shown for the worker.
  - field: `repo_branch`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the repository branch shown for the worker.
- response:
  - status: `200` when the handler returns normally.
  - media: `application/json`
  - body: object with `ok: bool`; `false` means the request lacked a usable container id or gate file path, and `true` means workflow state was marked blocked, the gate was recorded, and the dashboard broadcast completed.
  - field: `ok`; type boolean; required; default none; `false` when `container_id` or `file_path` normalizes to an empty string, otherwise `true` after the workflow mutation and broadcast succeed.
  - errors: no endpoint-specific error body is produced; Docker metadata lookup, render, or broadcast failures propagate as framework errors.

### post-push-exited

- does:
  - Receives the residual [exited push payload](../exited-push-payload.md) sent after the workflow process has returned, when the persistent sidecar socket is no longer authoritative for liveness.
  - Normalizes the payload `container_id` to a string and truncates it to the first 12 characters.
  - Rejects a missing normalized container id with `{"ok": false}` and no state mutation, Docker metadata lookup, gate clearing, or dashboard broadcast.
  - Ensures Docker volume metadata has been resolved for the workflow when possible before updating the visible fleet row.
  - Upserts the workflow with [workflow state](../concepts/workflow-state.md) `FINISHED`, applies non-null identity fields from the payload, records a numeric exit code when the payload contains one, and leaves any existing exit-code value unchanged when the payload value is absent or non-numeric.
  - Clears every open gate for that workflow so dashboard tabs stop presenting answer forms for a container that cannot act on an answer.
  - Broadcasts the dashboard shell after a successful finish update and returns `{"ok": true}`.
- code: groom/groom/app.py::push_exited
- route: `POST /push/exited`
- parent: [groom server](#groom-server)
- invocation: [receive-exited-push](#receive-exited-push)
- request:
  - method: `POST`
  - path: `/push/exited`
  - path variables: none
  - headers: none required by the handler.
  - query: none
  - body: JSON object matching [exited push payload](../exited-push-payload.md).
  - field: `container_id`; type string-convertible value; required for success; default none; normalized to `str(value)[:12]`.
  - field: `exit_code`; type integer or string containing optional leading `-` plus decimal digits; optional; default omitted; converted to `int` when numeric, otherwise omitted from the workflow update.
  - field: `name`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the workflow display name.
  - field: `repo_name`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the repository name shown for the worker.
  - field: `repo_branch`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null, updates the repository branch shown for the worker.
- response:
  - status: `200` when the handler returns normally.
  - media: `application/json`
  - body: object with `ok: bool`; `false` means the request lacked a usable container id, and `true` means workflow state was marked finished, open gates were cleared, and the shell broadcast completed.
  - field: `ok`; type boolean; required; default none; `false` on the validation-failure path and `true` only after volume metadata resolution, workflow upsert, gate clearing, and dashboard shell broadcast complete.
  - errors: no endpoint-specific error body is produced; Docker metadata lookup, render, or broadcast failures propagate as framework errors.
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code,
  groom/tests/test_app.py::test_push_exited_rejects_missing_container_id

### websocket-dashboard

- does:
  - Provides the [groom dashboard](../gui/screens/groom-dashboard.md) browser websocket used for live out-of-band shell updates and answer-form submissions.
  - Accepts the websocket upgrade, creates one unbounded process-local outbound queue for the connected browser tab, registers that queue before the initial snapshot is sent, and unregisters it in the session cleanup path.
  - Sends an initial out-of-band shell snapshot immediately after registration so a newly opened tab receives the current workflow fleet without waiting for the next server-side push.
  - Runs one outbound loop that waits for queued broadcast HTML fragments and sends each fragment as a websocket text frame; each frame is intended for htmx websocket out-of-band swaps or a small dashboard event script.
  - Runs one inbound [dashboard websocket receive loop](../concepts/dashboard-websocket-receive-loop.md) that receives JSON messages from browser `ws-send` answer forms and delegates every decoded frame to the command handler; only [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) objects whose `cmd` field is `answer` produce command-handler effects, while other commands are ignored with no response frame, state mutation, gate write, log entry, or broadcast.
  - Ends the websocket session when either the outbound send loop or inbound receive loop completes, then cancels the still-pending loop, propagates non-disconnect exceptions from the completed loop, and removes the client queue even when startup, rendering, sending, receiving, or command handling fails.
- code: groom/groom/app.py::dashboard_ws
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script,
  groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- route: `WS /ws`
- parent: [groom server](#groom-server)
- invocation: [run-dashboard-websocket-session](#run-dashboard-websocket-session)
- request:
  - method: websocket upgrade
  - path: `/ws`
  - query: none
  - headers: no endpoint-specific headers beyond the websocket upgrade handshake.
  - body: none before the websocket is accepted.
  - inbound-frame: JSON object messages decoded from browser text frames; answer submissions use [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md).
- response:
  - status: accepted websocket connection when the route handler starts normally.
  - media: websocket text frames.
  - initial-frame: one HTML fragment from `render.render_shell_data(..., oob=True)` representing the current dashboard shell state.
  - broadcast-frame: zero or more later HTML fragments received from the registered process-local client queue.
  - command-response: no per-message acknowledgement frame; answer success or failure is reflected through the next broadcast shell, and successful answers additionally include a `groom:answered` dashboard script.
  - errors: unknown `cmd` values are ignored; malformed websocket frames, send failures, and non-disconnect receive errors end the session through the framework rather than producing an endpoint-specific error payload.

### websocket-sidecar

- does:
  - Provides the persistent sidecar socket for [sidecar live sessions](../sidecar-live-sessions.md), distinct from the browser dashboard websocket, using [sidecar websocket frame](../sidecar-websocket-frame.md) JSON messages.
  - Accepts a websocket upgrade from a workflow-container sidecar; the sidecar is always the dialing client, so groom never needs inbound reachability into the container.
  - Ignores non-object JSON frames and ignores any frame other than a valid `hello` before sidecar identity has been established.
  - Requires the first useful `hello` frame to carry a non-empty `identity.container_id`; the handler string-normalizes and truncates that id to 12 characters.
  - Registers one [sidecar connection](../concepts/sidecar-connection.md) for the normalized container id in the [sidecar connection registry](../concepts/sidecar-connection-registry.md), displacing any previous sidecar socket for the same container.
  - Folds the `hello` frame's identity and snapshot into the visible workflow fleet through the [sidecar hello applier](../concepts/sidecar-hello-applier.md), rebuilding gates from the snapshot and broadcasting the resulting shell.
  - Resolves `rpc_result` frames against pending host-to-sidecar RPCs so `/files`, `/file`, `/diff`, and `/reload` can use the same connected socket.
  - Applies `progress` and `blocked` frames as live workflow state deltas and broadcasts the resulting dashboard updates.
  - Treats a websocket disconnect as normal session end and unregisters only the current connection, failing any in-flight RPCs so callers can fall back instead of hanging.
- code: groom/groom/app.py::dashboard_sidecar
- route: `WS /sidecar`
- parent: [groom server](#groom-server)
- invocation: [run-sidecar-websocket-session](#run-sidecar-websocket-session)
- request:
  - method: websocket upgrade
  - path: `/sidecar`
  - path variables: none
  - query: none
  - headers: no endpoint-specific headers beyond the websocket upgrade handshake.
  - body: none before the websocket is accepted.
  - inbound-frame: [sidecar websocket frame](../sidecar-websocket-frame.md) JSON object with `type` discriminator; supported inbound sidecar-to-groom types are `hello`, `rpc_result`, `progress`, and `blocked`.
  - field: `type`; type string; required for action; default absent; values other than `hello`, `rpc_result`, `progress`, or `blocked` are ignored.
  - field: `identity`; type object; required for a useful `hello`; default `{}`; contains sidecar identity fields.
  - field: `identity.container_id`; type string-convertible value; required for registration; default `""`; normalized to `str(value)[:12]`.
  - field: `identity.name`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null in `hello`, updates the workflow display name.
  - field: `identity.repo_name`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null in `hello`, updates the repository name shown for the worker.
  - field: `identity.repo_branch`; type any value accepted by the workflow model assignment; optional; default omitted; when non-null in `hello`, updates the repository branch shown for the worker.
  - field: `snapshot`; type object; optional for `hello`; default `{}`; carries the sidecar's current workflow node, terminal flag, and gate list.
  - field: `snapshot.current_node`; type string-compatible value; optional; default omitted; when truthy in `hello`, becomes the workflow's current node.
  - field: `snapshot.terminal`; type truthy/falsy value; optional; default falsey; truthy marks the workflow `FINISHED`, otherwise the rebuilt gate list decides `BLOCKED` vs `RUNNING`.
  - field: `snapshot.gates`; type array of objects; optional; default `[]`; each entry may contribute one open gate when its `file_path` is non-empty.
  - field: `snapshot.gates[].file_path`; type string-convertible value; required for a gate entry to be retained; default `""`; normalized to `str(value)` and used as the gate key.
  - field: `snapshot.gates[].question`; type string-convertible value; optional; default `""`; normalized to `str(value)` and stored as the gate question.
  - field: `id`; type string-convertible value; required for `rpc_result`; default `""`; correlation id of a pending host-issued RPC.
  - field: `ok`; type truthy/falsy value; optional for `rpc_result`; default false; converted to `bool(value)` for RPC resolution.
  - field: `data`; type any JSON value; optional for successful `rpc_result`; default `null`; delivered to the waiting RPC caller.
  - field: `error`; type string-convertible value; optional for failed `rpc_result`; default `""`; becomes the RPC failure message.
  - field: `current_node`; type any JSON value; optional for `progress`; default omitted; passed through to the workflow's current-node field.
  - field: `file_path`; type string-convertible value; required for `blocked`; default `""`; empty values are ignored.
  - field: `question`; type string-convertible value; optional for `blocked`; default `""`; stored as the gate question and truncated to 200 characters only for notification text.
- response:
  - status: accepted websocket connection when the route handler starts normally.
  - media: websocket JSON text frames sent by host-side sidecar operations.
  - outbound-frame: `{"type":"rpc","id":string,"method":"getTree"|"getFile"|"getDiff","params":object}` when HTTP data-plane handlers need file-tree, file-content, or diff data from the sidecar.
  - outbound-frame: `{"type":"reload"}` when the reload endpoint targets this connected sidecar.
  - command-response: no acknowledgement for `hello`, `progress`, or `blocked`; their success is visible through dashboard shell broadcasts on the browser websocket. `rpc_result` resolves an in-process future and does not send a reply frame.
  - errors: malformed JSON, receive failures other than ordinary websocket disconnect, send failures on host-issued frames, and failures while folding/broadcasting state end through the framework or the waiting caller rather than producing an endpoint-specific error payload.
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate,
  groom/tests/test_app.py::test_apply_hello_running_when_no_gates,
  groom/tests/test_app.py::test_apply_hello_finished_when_terminal,
  groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively,
  groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection

### post-reload

- does:
  - Receives the development-loop reload request for the connected [sidecar live sessions](../sidecar-live-sessions.md).
  - Targets exactly the requested sidecar when `container_id` is non-empty; the value is used as supplied by the query parser and is not truncated, normalized, or matched by prefix.
  - When `container_id` is empty, snapshots every currently connected sidecar id from the [sidecar connection registry](../concepts/sidecar-connection-registry.md) before the first reload send, so later connects or disconnects are outside this request's target set.
  - Looks up each target in the [sidecar connection registry](../concepts/sidecar-connection-registry.md) and sends one websocket reload command through the target's [sidecar connection](../concepts/sidecar-connection.md) only when that lookup still returns a live connection.
  - Counts only sidecars whose connection accepted the reload command.
  - Treats missing connections and send failures as per-sidecar no-ops; failed sends are not counted, do not remove registry entries, and do not stop later targets from being attempted.
  - Returns only the count of reload commands accepted by sidecars; it does not wait for container restart or reconnection.
- code: groom/groom/app.py::reload
- route: `POST /reload`
- parent: [groom server](#groom-server)
- invocation: [reload-sidecars](#reload-sidecars)
- request:
  - method: `POST`
  - path: `/reload`
  - path variables: none
  - query: `container_id` string, optional, default `""`; when empty, all connected sidecars are targeted.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: object with `ok: true` and `reloaded`, the number of sidecars that accepted the reload command. `reloaded` may be `0` when no target is connected or every target send fails.
  - field: `ok`; type boolean; required; default none; always `true` on the handler's normal return path.
  - field: `reloaded`; type integer; required; default none; count of target sidecar connections whose reload websocket frame send completed without raising.
  - errors: no endpoint-specific error body is produced; absent sidecars and dead sockets are swallowed as no-op targets, while request parsing failures are framework-level failures.
- verify: groom/tests/test_app.py::test_reload_broadcasts_to_all_connected_sidecars,
  groom/tests/test_app.py::test_reload_targets_one_container_when_id_given

### get-static-assets

- does:
  - Serves vendored dashboard assets from the package asset directory mounted at `/assets` by `create_app`.
  - Resolves every requested asset path relative to the [Groom app module](../concepts/groom-app-module.md#field-assets-dir) package path `groom/groom/assets`, not the process working directory.
  - Exists because `create_app` includes one static-files router in the application route handlers alongside the first-party HTTP and websocket handlers.
  - Keeps the dashboard independent of runtime CDN access for htmx, the htmx websocket extension, diff2html, marked, DOMPurify, highlight.js, diff CSS, highlight CSS, and dashboard CSS.
  - Runs no first-party per-request handler for an individual asset request; after route matching, validation, lookup, response metadata, and not-found handling belong to the mounted static-file router.
  - Does not read query parameters, request body, cookies, workflow state, Docker state, or sidecar connection state.
  - Does not mutate server state, schedule discovery, broadcast websocket updates, or proxy asset requests to any remote host.
- code: groom/groom/app.py::create_app
- route: `GET /assets/*`
- parent: [groom server](#groom-server)
- invocation: [serve-static-asset](#serve-static-asset)
- request:
  - method: `GET`
  - path: `/assets/{path...}`
  - path variable: `path` string, required, no default; interpreted by the mounted static-file router as a path below `groom/groom/assets`.
  - examples: `htmx.min.js`, `htmx-ext-ws.min.js`, `diff2html.min.js`, `diff2html.min.css`, `marked.min.js`, `purify.min.js`, `highlight.min.js`, `hljs-github-dark.min.css`, and `dashboard.css`.
  - query: none consumed by groom; query strings, when present, do not select workflow, sidecar, or dashboard state.
  - headers: none required by groom; cache and conditional request handling, when present, is framework static-file behavior.
  - body: none
- response:
  - status: `200` for an existing requested asset; missing files, unsupported methods, and conditional request outcomes use the framework static-file response for the mounted router.
  - media: derived from the requested asset type by the static-file response.
  - body: bytes of the matched packaged asset; no application JSON or HTML fragment envelope is added by groom.
  - errors: no endpoint-specific error body is produced by groom; absent assets and invalid static-file requests are handled by the mounted framework router.

## Invocations

### schedule-startup-discovery-scan

- on: [groom server](#groom-server)
- trigger: Litestar runs the server application's startup hooks for the app returned by `create_app`.
- when:
  - The groom process has constructed the Litestar application and the event loop is running startup lifecycle hooks.
  - `create_app` registered `_spawn_scan` as the only first-party startup hook in `on_startup`.
  - `state.SCANNING` already starts true from module initialization, so this hook does not need to set the discovery-loading flag before scheduling work.
  - No request, connected dashboard websocket, sidecar websocket, Docker availability, workflow registry entry, or operator action is required.
- does:
  - Enters `groom/groom/app.py::_spawn_scan` as an async startup hook with no parameters.
  - Creates one background task for `groom/groom/app.py::_background_scan()` on the current event loop, so the initial Docker discovery pass can run after startup begins without blocking the server application on the whole scan.
  - Stores the created task in the module-level `_scan_task` slot, keeping a strong reference to the scheduled background work while it runs; later startups in the same process would replace that slot with the latest task handle.
  - Returns `None` immediately after task creation; it does not await the discovery pass, inspect Docker containers, mutate the workflow registry, clear `state.SCANNING`, render dashboard HTML, broadcast websocket updates, or handle scan failures in the startup hook itself.
  - The scheduled [startup background discovery scan](../concepts/startup-background-discovery-scan.md) then runs one [reconcile workflow fleet](../concepts/workflow-registry.md#method-reconcile-workflow-fleet) pass, allowing discovered workflow containers to replace registry entries and allowing vanished containers to be pruned when Docker presence can be read.
  - The scheduled scan always clears the [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md) after the reconciliation attempt exits, so successful scans and reconciliation errors both stop advertising startup discovery as in flight.
  - After clearing the scanning flag, the scheduled scan calls the [dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md) so connected dashboard websocket clients receive an out-of-band shell fragment for the current workflow registry and non-loading discovery state.
  - If reconciliation or completion broadcast raises, the exception belongs to the background task rather than the startup hook; the startup hook has already returned after scheduling the task.
- emits: one scheduled in-process background task for the startup discovery scan; no HTTP response, websocket frame, sidecar frame, browser event, log entry, or persisted artifact.
- consumes: the current asyncio event loop, the startup lifecycle call from the Litestar application, the first-party [startup background discovery scan](../concepts/startup-background-discovery-scan.md) coroutine, the [workflow registry](../concepts/workflow-registry.md), the [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md), and the [dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md).
- code: groom/groom/app.py::_spawn_scan
- verify: groom/tests/test_app.py::test_spawn_scan_returns_before_discovery_completes
- request:
  - method: none; this is a server startup lifecycle invocation, not an HTTP route or websocket message.
  - path: none
  - path variables: none
  - query: none
  - headers: none
  - body: none
- response:
  - status: none; successful completion means the startup hook coroutine returned after scheduling the task.
  - media: none
  - body: none
  - errors: task creation failures propagate out of the startup hook; reconciliation or completion-broadcast failures raised later by the background task do not change the startup hook's already-returned result.

### serve-root-dashboard-html

- on: [get-root-dashboard-html](#get-root-dashboard-html)
- trigger: a browser, health probe, or other HTTP client requests `GET /` from the groom server.
- when:
  - The groom process has started successfully and the Litestar route table includes the root route.
  - `groom/groom/app.py` imported successfully, including the package-local dashboard template preload into [field-dashboard-html](../concepts/groom-app-module.md#field-dashboard-html).
  - No request query, path, header, cookie, or body data is required.
- does:
  - Enters `groom/groom/app.py::index` for the root route.
  - Reads no request-derived inputs; path matching is complete before this handler runs, and there are no handler parameters for path variables, query values, headers, cookies, or request body data.
  - Builds a `200 OK` HTML response whose content is the module-level `_DASHBOARD_HTML` byte string loaded from `groom/groom/templates/dashboard.html` when `groom/groom/app.py` was imported.
  - Sets the response media type to `text/html` through Litestar's HTML media type, so the client receives the packaged dashboard shell as an HTML document rather than as an HTML fragment or JSON payload.
  - Leaves the returned HTML document unchanged: no workflow rows, status counts, gate details, repository options, file data, diff data, websocket messages, or sidecar state are rendered by this invocation.
  - Leaves dashboard liveness, workflow discovery state, websocket registration, and dynamic inbox/status rendering to later dashboard requests and websocket connections.
  - Calls no first-party helper function and reads no mutable first-party state during the request; the only first-party artifact consumed by this layer is the already documented dashboard template.
- emits: exactly one HTTP response; this invocation does not broadcast websocket frames, enqueue sidecar messages, dispatch browser events, or write logs.
- consumes: the route match for `GET /` and packaged [groom dashboard](../gui/screens/groom-dashboard.md) HTML bytes from `groom/groom/templates/dashboard.html` via [field-dashboard-html](../concepts/groom-app-module.md#field-dashboard-html).
- code: groom/groom/app.py::index
- request:
  - method: `GET`
  - path: `/`
  - path variables: none
  - query: none
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/html`
  - body: exact static dashboard shell bytes from `groom/groom/templates/dashboard.html`; clients interpret this as the [groom dashboard](../gui/screens/groom-dashboard.md) screen and then load its linked vendored assets from the static asset mount.
  - errors: none intentionally emitted by this handler; route matching, response construction, or import-time template-read failures are framework/process-level failures rather than endpoint-specific error responses.

### serve-search-fragment

- on: [get-search-fragment](#get-search-fragment)
- trigger: a dashboard search request or other HTTP client requests `GET /search`, optionally with a `q` query string.
- when:
  - The groom process has started successfully and the Litestar route table includes the search route.
  - The in-memory workflow registry may be empty, partially discovered, or populated; no Docker or sidecar availability is required.
  - The request body is ignored and no headers, cookies, or path variables are required.
- does:
  - Enters `groom/groom/app.py::search` for the search route and receives `q` as a string with default `""`.
  - Reads a new membership snapshot of all current [workflow containers](../concepts/workflow-container.md) from the [workflow registry](../concepts/workflow-registry.md) through the [all workflows snapshot](../concepts/workflow-registry.md#method-all-workflows-snapshot) helper; the helper returns the current registry values as a list without sorting, filtering, cloning, or mutating them.
  - Calls `render.render_inbox(workflows, q, oob=True)` to produce the filtered [operator inbox](../operator-inbox.md) fragment, passing the query string unchanged and requiring an out-of-band `#inbox-list` replacement root.
  - Includes only workflows with open gates in the fragment; non-gated running, idle, or finished workers remain outside the operator inbox.
  - Applies a case-insensitive substring query over workflow name, repository name, repository branch, workflow type, current node, and each open gate file path; workflow container ids and gate question text are not searched.
  - Sorts matching gated workflows by dashboard state priority, with blocked before running before idle before finished, and then by workflow name inside a state.
  - Emits the in-flight discovery loading state only when the result set is empty, process discovery is currently scanning, and `q` is empty; an empty non-empty-query result always emits the normal inbox empty state.
  - Preserves the dashboard-wide status counts by omitting the status bar from the response; this request never recomputes or scopes fleet totals to `q`.
  - Returns `200 OK` with HTML media type and the out-of-band `#inbox-list` replacement fragment; the response body is exactly the renderer output and contains no status-bar fragment, worker detail fragment, answer form, websocket script, or sidecar data.
  - Does not mutate workflow state, trigger discovery, query Docker, contact sidecars, broadcast websocket updates, or write gate files.
- emits: one `text/html` HTTP response containing the [operator inbox](../operator-inbox.md) root fragment; no websocket frame, sidecar frame, browser event script, Docker request, answer write, log entry, or persisted artifact is emitted.
- consumes: the `GET /search` route match, the optional `q` query string, the current in-memory [workflow registry](../concepts/workflow-registry.md), the [dashboard discovery scanning flag](../concepts/dashboard-discovery-scanning-flag.md) when an empty unfiltered inbox must choose loading vs empty state, and the [operator inbox](../operator-inbox.md) rendering contract.
- code: groom/groom/app.py::search
- request:
  - method: `GET`
  - path: `/search`
  - path variables: none
  - query: `q` string, optional, default `""`; empty disables filtering, non-empty filters visible inbox rows.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/html`
  - body: exactly one `<div class="inbox-list" id="inbox-list" hx-swap-oob="true">…</div>` HTML fragment suitable for htmx replacement in the [groom dashboard](../gui/screens/groom-dashboard.md); the inner content is zero or more inbox rows, the normal empty-state message, or the discovery loading message when scanning and unfiltered.
  - errors: none intentionally emitted by this handler; request parsing failures and renderer failures are framework-level failures rather than endpoint-specific response bodies.

### serve-repository-menu

- on: [get-repository-menu](#get-repository-menu)
- trigger: the dashboard repository picker, or another HTTP client, requests `GET /repos` from the groom server.
- when:
  - The groom process has started successfully and the Litestar route table includes the repository menu route.
  - The in-memory workflow registry may be empty, partially discovered, or populated.
  - Only workflows with a non-empty workspace volume are eligible for menu entries.
  - No request query, path, header, cookie, or body data is required.
- does:
  - Enters `groom/groom/app.py::repos` for the repository menu route.
  - Reads a snapshot list of all current [workflow containers](../concepts/workflow-container.md) from the [workflow registry](../concepts/workflow-registry.md) through the [all workflows snapshot](../concepts/workflow-registry.md#method-all-workflows-snapshot) helper; the snapshot is a list of current registry values and is not sorted, cloned, filtered, or mutated by the helper.
  - Filters out workflows whose `workspace_volume` is empty so pending or incompletely discovered containers are absent from the menu.
  - For each remaining workflow, asks the [workspace volume repository-directory reader](../concepts/workspace-volume-repository-directory-reader.md) for volume-relative git checkout directories, running those per-workflow reads concurrently through worker-thread calls when at least one eligible workflow exists.
  - During each checkout-discovery call, mounts the workflow workspace volume read-only and accepts only `.git` directories found one or two directory levels below the volume root.
  - Normalizes each accepted `.git` path into its volume-relative parent checkout directory, sorts the checkout directory list, and treats a non-zero Docker discovery process as an empty checkout list.
  - Skips checkout discovery entirely when no workflows are eligible and passes an empty entry list directly to the renderer.
  - Treats an empty checkout list as a browsable volume-root entry for that workflow, while Docker errors inside checkout discovery surface as that same empty checkout list.
  - Assembles [repository menu data](../repository-menu-data.md) as `(workflow, repo_dirs)` tuples, preserving one tuple per eligible workflow.
  - Calls the [groom render module](../concepts/groom-render-module.md#method-render-repo-menu) to produce the HTML fragment consumed by the [groom dashboard](../gui/screens/groom-dashboard.md) repository overlay.
  - Orders rendered options by workflow state order, then workflow name, then the sorted checkout directory list for each workflow; each rendered checkout becomes a [repository menu option](../gui/screens/groom-dashboard.md#repository-menu-option) with `role="option"`, `data-container`, `data-repo`, `data-label`, a workflow state dot, an optional workflow type badge, and a visible label.
  - Emits the non-interactive `No repositories available.` empty-state fragment when no eligible workflows exist, and emits one volume-root option for any eligible workflow whose checkout-discovery list is empty.
  - Returns `200 OK` with HTML media type and no out-of-band swap wrapper; the dashboard is responsible for inserting the fragment into the already-open repository overlay and filtering option rows client-side.
  - Does not mutate workflow state, trigger discovery, contact sidecar sockets, broadcast websocket updates, read file contents, compute diffs, accept repository search input, or validate a chosen repository path.
- emits: one `text/html` HTTP response containing zero or more [repository menu option](../gui/screens/groom-dashboard.md#repository-menu-option) rows, or the non-interactive repository-menu empty state; no websocket frame, sidecar frame, browser event script, Docker mutation, workflow-state mutation, persisted artifact, or out-of-band htmx fragment is emitted.
- consumes: the `GET /repos` route match, the current in-memory [workflow registry](../concepts/workflow-registry.md), each eligible workflow's `workspace_volume` field from [workflow container](../concepts/workflow-container.md), checkout directory lists from the [workspace volume repository-directory reader](../concepts/workspace-volume-repository-directory-reader.md), and the [repository menu data](../repository-menu-data.md) rendering contract.
- code: groom/groom/app.py::repos
- verify: groom/tests/test_app.py::test_repos_endpoint_lists_one_entry_per_container_repo
- request:
  - method: `GET`
  - path: `/repos`
  - path variables: none
  - query: none
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/html`
  - body: concatenated repository picker option HTML derived from [repository menu data](../repository-menu-data.md), or `<div class="repo-empty">No repositories available.</div>` when no eligible workflow entries exist. Each option row is `<div class="repo-item" role="option" data-container="..." data-repo="..." data-label="...">…</div>` with dynamic attribute and label values HTML-escaped by the renderer.
  - errors: none intentionally emitted by this invocation; request parsing failures are framework-level failures, checkout discovery failures for a volume collapse to an empty checkout list for that workflow, and unexpected Docker process-launch or timeout exceptions from checkout discovery propagate as framework-level failures rather than endpoint-specific response bodies.

### serve-workspace-file-list

- on: [get-workspace-file-list](#get-workspace-file-list)
- trigger: the dashboard Files panel, or another HTTP client, requests `GET /files/{container_id}` with an optional `repo` query string.
- when:
  - The groom process has started successfully and the Litestar route table includes the file-list route.
  - `container_id` is supplied as a path variable; it may or may not correspond to a known workflow or connected sidecar.
  - `repo` may be empty, a volume-relative checkout directory from the repository picker, or any other string accepted by the downstream sidecar/fallback readers.
  - No request headers, cookies, or body data are required.
- does:
  - Enters `groom/groom/app.py::files` for the file-list route and receives `container_id` plus `repo` with default `""`.
  - Calls `_sidecar_rpc(container_id, "getTree", {"repo": repo})` to ask the connected sidecar, if any, for the selected checkout's [workspace file list data](../workspace-file-list-data.md).
  - The [sidecar RPC helper](../concepts/sidecar-rpc-helper.md) looks up the current [sidecar connection](../concepts/sidecar-connection.md) for `container_id`; when none is registered it returns `None` immediately without mutating state or attempting any Docker fallback itself.
  - When a connection is registered, the helper sends exactly one `rpc` [sidecar websocket frame](../sidecar-websocket-frame.md) with method `getTree` and params `{"repo": repo}` through the connection's RPC method, then returns the sidecar result unchanged on success.
  - If that sidecar RPC fails through timeout, socket send failure, sidecar error result, sidecar disconnect, or registry displacement reported as `SidecarError`, the helper converts the failure to `None`; this invocation treats that the same as an absent sidecar and continues to the volume-read fallback.
  - If the sidecar RPC returns a dictionary, reads its `paths` value, treats a missing or falsey `paths` value as an empty list, joins the paths with newline separators, and returns `200 OK` with `text/plain` media type without reading `state.WORKFLOWS` or consulting Docker volumes.
  - If the sidecar path is unavailable, looks up `container_id` in `state.WORKFLOWS` and extracts `workspace_volume` when the [workflow container](../concepts/workflow-container.md) is known.
  - If no workflow or workspace volume is known, returns `200 OK` with `text/plain` media type and an empty body.
  - If a workspace volume is known, calls `docker_io.list_files(workspace_volume, repo)` on a worker thread to read the selected checkout through the [workspace volume file-list reader](../concepts/workspace-volume-file-list-reader.md).
  - The fallback reader mounts the workflow volume read-only at `/vol`, searches `/vol/{repo}` when `repo` is non-empty or `/vol` when it is empty, prunes `.git`, `node_modules`, `__pycache__`, and `.venv` directories, and returns only regular-file paths relative to the selected checkout root.
  - If the fallback Docker process exits non-zero, the reader returns an empty list; subprocess launch or timeout exceptions are not caught by this handler and therefore become framework-level failures rather than endpoint-specific empty responses.
  - Joins the fallback path list with newline separators in the reader's sorted order and returns `200 OK` with `text/plain` media type as [workspace file list data](../workspace-file-list-data.md).
  - Leaves panel rendering, directory expansion, file-row activation, and empty-state presentation to the [groom dashboard](../gui/screens/groom-dashboard.md); this invocation returns data only.
  - Does not mutate `state.WORKFLOWS`, register or unregister sidecars, broadcast websocket fragments, run discovery, read individual file content, compute diffs, or raise endpoint-specific error responses for unavailable data.
- emits: one `text/plain` HTTP response; no websocket frame, sidecar frame, browser event script, Docker mutation, workflow-state mutation, persisted artifact, or dashboard broadcast is emitted.
- consumes: optional sidecar RPC result shaped as `{paths: list[str]}` from [sidecar live sessions](../sidecar-live-sessions.md) through the [sidecar RPC helper](../concepts/sidecar-rpc-helper.md), or fallback [workspace file list data](../workspace-file-list-data.md) from the [workspace volume file-list reader](../concepts/workspace-volume-file-list-reader.md).
- code: groom/groom/app.py::files
- verify: groom/tests/test_app.py::test_files_endpoint_returns_newline_separated_paths,
  groom/tests/test_app.py::test_files_prefers_sidecar_socket_when_connected,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors
- request:
  - method: `GET`
  - path: `/files/{container_id}`
  - path variable: `container_id` string, required, no default; selected workflow container id from dashboard state and sidecar registration state.
  - query: `repo` string, optional, default `""`; selected volume-relative checkout directory, passed unchanged to the sidecar `getTree` params and fallback workspace-volume reader.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/plain`
  - body: newline-separated repo-relative paths matching [workspace file list data](../workspace-file-list-data.md), joined without adding a required trailing newline, or an empty string when no sidecar or fallback data is available.
  - errors: none intentionally emitted by this invocation; absent workflow state, absent workspace volume, sidecar RPC failure, and fallback reader non-zero exit are represented as an empty `200 OK` text response or fallback data. Request parsing failures, Docker process-launch exceptions, and Docker timeout exceptions propagate as framework-level failures.

### serve-workspace-file-content

- on: [get-workspace-file-content](#get-workspace-file-content)
- trigger: the dashboard Files panel, or another HTTP client, requests `GET /file/{container_id}` with optional `repo` and `path` query strings.
- when:
  - The groom process has started successfully and the Litestar route table includes the file-content route.
  - `container_id` is supplied as a path variable; it may or may not correspond to a known workflow or connected sidecar.
  - `repo` may be empty, a volume-relative checkout directory from the repository picker, or any other string accepted by the downstream sidecar/fallback readers.
  - `path` may be empty, a repo-relative file path from the Files panel tree, or any other string accepted or rejected by the downstream sidecar/fallback readers.
  - No request headers, cookies, or body data are required.
- does:
  - Enters `groom/groom/app.py::file_content` for the file-content route and receives `container_id`, `repo`, and `path` with string defaults of `""` for the query values.
  - Calls `_sidecar_rpc(container_id, "getFile", {"repo": repo, "path": path})` to ask the connected sidecar, if any, for the selected file content.
  - If the sidecar RPC returns a dictionary, reads its `content` value, substitutes `""` when the value is missing or falsey, and returns `200 OK` with `text/plain` media type without consulting Docker volumes.
  - If the sidecar path is unavailable, looks up `container_id` in `state.WORKFLOWS` and extracts `workspace_volume` when the workflow is known.
  - Builds the fallback relative path as `f"{repo}/{path}".lstrip("/")` when `repo` is non-empty, otherwise uses `path` unchanged.
  - If no workspace volume is known or the fallback relative path is empty, returns `200 OK` with `text/plain` media type and an empty body.
  - If a workspace volume and non-empty relative path are known, calls the [workspace volume file-content reader](../concepts/workspace-volume-file-content-reader.md) on a worker thread to validate the volume-relative path, mount the workflow volume read-only at `/vol`, and read `/vol/{repo/path}` through a throwaway Alpine `cat` process.
  - If the fallback reader rejects the relative path with `ValueError`, returns `200 OK` with `text/plain` media type and an empty body; no fallback Docker process is started for rejected paths.
  - If the fallback Docker read process exits non-zero because the file is missing, unreadable, or otherwise unavailable, treats the reader's `None` result as an empty body with the same `200 OK` text response contract.
  - Returns the fallback reader's raw stdout when it is truthy; otherwise returns an empty body with the same `200 OK` text response contract, so empty files and unavailable files are indistinguishable to the HTTP client.
  - Leaves syntax highlighting, filename display, empty-state presentation, and focus/state updates to the [groom dashboard](../gui/screens/groom-dashboard.md); this invocation returns data only.
  - Does not mutate `state.WORKFLOWS`, register or unregister sidecars, broadcast websocket fragments, run discovery, list directory contents, compute diffs, or emit endpoint-specific error responses for unavailable data.
- emits: one `text/plain` HTTP response; no websocket frame, sidecar frame, browser event script, Docker mutation, workflow-state mutation, persisted artifact, or dashboard broadcast is emitted.
- consumes: the selected `container_id`, `repo`, and `path` request values; optional sidecar RPC result shaped as `{content: str}` from [sidecar live sessions](../sidecar-live-sessions.md) through the [sidecar RPC helper](../concepts/sidecar-rpc-helper.md); and, when the sidecar path is unavailable, the [workflow registry](../concepts/workflow-registry.md) workspace-volume value plus fallback [workspace file content data](../workspace-file-content-data.md) from the [workspace volume file-content reader](../concepts/workspace-volume-file-content-reader.md).
- code: groom/groom/app.py::file_content
- verify: groom/tests/test_app.py::test_file_content_prefers_sidecar_socket,
  groom/tests/test_app.py::test_file_endpoint_joins_repo_and_path_and_returns_content,
  groom/tests/test_app.py::test_file_endpoint_swallows_unsafe_path
- request:
  - method: `GET`
  - path: `/file/{container_id}`
  - path variable: `container_id` string, required, no default; selected workflow container id from dashboard state and sidecar registration state.
  - query: `repo` string, optional, default `""`; selected volume-relative checkout directory.
  - query: `path` string, optional, default `""`; selected repo-relative file path.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/plain`
  - body: [workspace file content data](../workspace-file-content-data.md), serialized as raw file text from the selected checkout or an empty string when the sidecar and fallback paths cannot supply file content.
  - errors: none intentionally emitted by this invocation; absent workflow state, absent workspace volume, absent or failed sidecar RPCs, empty selected paths, traversal-guard failures, missing files, unreadable files, and empty reader output are represented as an empty `200 OK` text response or sidecar/fallback data. Request parsing failures and unexpected reader exceptions other than traversal rejection propagate as framework-level failures.

### serve-workspace-diff

- on: [get-workspace-diff](#get-workspace-diff)
- trigger: the dashboard Diff panel, the selected worker's working-tree diff disclosure, or another HTTP client requests `GET /diff/{container_id}` with an optional `repo` query string.
- when:
  - The groom process has started successfully and the Litestar route table includes the workspace-diff route.
  - `container_id` is supplied as a path variable; it may or may not correspond to a known workflow or connected sidecar.
  - `repo` may be empty, a volume-relative checkout directory from the repository picker, or any other string accepted by the downstream sidecar/fallback readers.
  - No request headers, cookies, or body data are required.
- does:
  - Enters `groom/groom/app.py::diff` for the workspace-diff route and receives `container_id` plus `repo` with default `""`.
  - Calls `_sidecar_rpc(container_id, "getDiff", {"repo": repo})` to ask the connected sidecar, if any, for the selected checkout's [workspace diff data](../workspace-diff-data.md).
  - If the sidecar RPC returns a dictionary, reads its `diff` value, substitutes `""` when the value is missing or falsey, and returns `200 OK` with `text/plain` media type without consulting Docker volumes.
  - If the sidecar path is unavailable, looks up `container_id` in `state.WORKFLOWS` and extracts `workspace_volume` when the workflow is known.
  - If no workspace volume is known, returns `200 OK` with `text/plain` media type and an empty body.
  - If a workspace volume is known, calls the [workspace volume diff reader](../concepts/workspace-volume-diff-reader.md) on a worker thread to collect the selected checkout's raw unified diff through a throwaway read-only git container.
  - Passes the `repo` query value unchanged to the fallback reader; an empty `repo` asks the reader to choose the first discovered checkout, while a non-empty value is treated as the volume-relative checkout path.
  - Returns the fallback diff text as-is with `text/plain` media type; no discovered checkout, a non-zero git/Docker exit, or no working-tree changes remain an empty `200 OK` response.
  - Leaves diff2html rendering, file-list presentation, empty-state presentation, and focus/state updates to the [groom dashboard](../gui/screens/groom-dashboard.md); this invocation returns data only.
  - Does not mutate `state.WORKFLOWS`, register or unregister sidecars, broadcast websocket fragments, run discovery, list files, read individual file contents, or emit endpoint-specific error responses for unavailable diff data.
- emits: one `text/plain` HTTP response; no websocket frame, sidecar frame, browser event script, Docker mutation, workflow-state mutation, persisted artifact, or dashboard broadcast is emitted.
- consumes: optional sidecar RPC result shaped as `{diff: str}` from [sidecar live sessions](../sidecar-live-sessions.md), or fallback [workspace diff data](../workspace-diff-data.md) from the [workspace volume diff reader](../concepts/workspace-volume-diff-reader.md).
- code: groom/groom/app.py::diff
- verify: groom/tests/test_app.py::test_diff_prefers_sidecar_socket,
  groom/tests/test_app.py::test_diff_endpoint_passes_repo_through
- request:
  - method: `GET`
  - path: `/diff/{container_id}`
  - path variable: `container_id` string, required, no default; selected workflow container id from dashboard state and sidecar registration state.
  - query: `repo` string, optional, default `""`; selected volume-relative checkout directory.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/plain`
  - body: [workspace diff data](../workspace-diff-data.md), serialized as raw unified git diff text from the selected checkout or an empty string when the sidecar path has no diff, no workspace volume is known, no fallback checkout is discovered, the fallback git/Docker process exits non-zero, or the selected checkout has no working-tree diff.
  - errors: none intentionally emitted by this invocation; absent workflow state, absent workspace volume, absent or failed sidecar RPCs, no discovered fallback checkout, non-zero fallback git/Docker completion, and empty diff output are represented as an empty `200 OK` text response or sidecar/fallback data. Request parsing failures and unexpected sidecar-registry, Docker process-launch, Docker timeout, or response-construction exceptions propagate as framework-level failures.

### serve-worker-detail

- on: [get-worker-detail](#get-worker-detail)
- trigger: the dashboard inbox row activation or another HTTP client requests `GET /worker/{container_id}` for one workflow container.
- when:
  - The groom process has started successfully and the Litestar route table includes the worker-detail route.
  - `container_id` is supplied as a path variable; it may correspond to a known workflow in memory or to no current workflow.
  - No query string, request headers, cookies, or request body are required.
- does:
  - Enters `groom/groom/app.py::worker_detail` for the worker-detail route and receives `container_id` as a string path parameter.
  - Reads `state.WORKFLOWS.get(container_id)` once to obtain the current in-memory [workflow container](../concepts/workflow-container.md), or `None` when the id is unknown.
  - Calls the [worker detail renderer](../concepts/worker-detail-renderer.md) with that value to build the dashboard detail-pane HTML fragment.
  - For an unknown worker, returns a `#detail` fragment containing the `Worker not found.` empty state.
  - For a known worker with no open gates, returns the worker header and a `No open gate` message that includes the workflow state and current node when present.
  - For a known worker with open gates, returns the worker header, gate blocks sorted by gate file path, escaped gate-question markdown for client-side sanitized rendering, websocket answer forms scoped by hidden `workflow_id` and `file_path` fields, and exactly one working-tree diff disclosure carrying the worker container id.
  - Ensures every dynamic detail-fragment value produced by the renderer path is HTML-escaped before it enters text nodes or attributes; gate questions remain escaped text in `data-md` nodes for the dashboard's client-side markdown sanitizer.
  - Builds a `200 OK` HTML response and leaves client-side markdown rendering, answer submission, diff fetching, and detail-pane replacement to the [groom dashboard](../gui/screens/groom-dashboard.md).
  - Does not mutate `state.WORKFLOWS`, register sidecars, start discovery, query Docker, broadcast websocket fragments, write gate files, or compute workspace diffs.
- emits: one `text/html` HTTP response; no websocket frame, sidecar frame, browser event script, Docker mutation, workflow-state mutation, persisted artifact, or dashboard broadcast is emitted.
- consumes: optional in-memory [workflow container](../concepts/workflow-container.md) state from `state.WORKFLOWS`, including workflow identity, state, current node, open gates, and gate questions; the [worker detail renderer](../concepts/worker-detail-renderer.md) consumes that record as its only input.
- code: groom/groom/app.py::worker_detail
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form,
  groom/tests/test_render.py::test_worker_detail_has_one_diff_disclosure,
  groom/tests/test_render.py::test_worker_detail_not_found_and_no_gate_states
- request:
  - method: `GET`
  - path: `/worker/{container_id}`
  - path variables: `container_id` string, required, no default; exact workflow container id used as the registry lookup key.
  - query: none
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200`
  - media: `text/html`
  - body: selected worker detail-pane fragment for the dashboard `#detail` region; the outer element is always `<div id="detail">`, with the unknown-worker empty state, no-open-gate status state, or open-gate gate-list state selected by the renderer.
  - errors: none intentionally emitted by this handler; an unknown workflow id is a successful empty-state fragment, and request parsing or renderer failures are framework-level failures rather than endpoint-specific error bodies.

### refresh-workflow-fleet

- on: [post-refresh](#post-refresh)
- trigger: the dashboard refresh control, or another HTTP client, requests `POST /refresh` from the groom server.
- when:
  - The groom process has started successfully and the Litestar route table includes the refresh route.
  - No path variables, query string, request headers, cookies, or request body are required.
  - The in-memory workflow registry may be empty, partially discovered, populated from earlier pushes, or carrying stale entries for containers that no longer exist.
  - No in-process lock or idempotency key prevents another refresh request from running at the same time.
- does:
  - Enters `groom/groom/app.py::refresh` for the refresh route.
  - Sets `state.SCANNING` to `True` before any Docker discovery work starts.
  - Calls the [dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md) once immediately after setting `SCANNING`; if this pre-scan broadcast succeeds, connected dashboard websocket clients are offered an out-of-band shell update that can display the scanning state.
  - The pre-scan broadcaster call snapshots `state.WORKFLOWS`, renders the inbox/list region plus status bar as out-of-band shell HTML, and queues that same fragment for every browser dashboard websocket client registered at that moment; it does not send to sidecar sockets, mutate workflow records, or append notification scripts.
  - Calls the [reconcile workflow fleet](../concepts/workflow-registry.md#method-reconcile-workflow-fleet) registry method only after the pre-scan broadcast succeeds.
  - During reconciliation, collects discoverable [workflow containers](../concepts/workflow-container.md) from one Docker discovery scan and assigns each returned record into `state.WORKFLOWS` by `container_id`, replacing any older in-memory record for the same container id.
  - After discovered records have been installed, queries the current Docker container-id set and prunes vanished workflow entries only when that present-id query returns a set.
  - If the present-id query returns `None` because Docker is unavailable, preserves every existing registry entry rather than treating the failed lookup as an empty fleet.
  - Receives the reconciliation count as the number of workflow containers returned by the scan before pruning, not the final registry size and not the number of upserts or removals.
  - Sets `state.SCANNING` to `False` in a `finally` block around the reconciliation call, so successful reconciliation and raised reconciliation errors both clear the process-level scanning state.
  - On successful reconciliation, calls the [dashboard shell broadcaster](../concepts/dashboard-shell-broadcaster.md) a second time so connected dashboard tabs are offered the refreshed fleet state after upserts and safe pruning.
  - The post-scan broadcaster call repeats the current-registry snapshot/render/queue sequence after `state.SCANNING` has been cleared; if rendering or queueing raises, reconciliation has already completed and the endpoint fails before returning its success JSON.
  - Returns a JSON object with `ok` set to `true` and `count` set to the number of workflow containers returned by the scan only after the post-scan broadcast succeeds.
  - If the pre-scan `_broadcast_shell()` raises, does not call `_reconcile()`, does not clear `state.SCANNING`, does not send the post-scan broadcast, and does not return an endpoint-specific error body.
  - If `_reconcile()` raises, clears `state.SCANNING`, skips the post-scan broadcast, and lets the framework produce the error response.
  - If the post-scan `_broadcast_shell()` raises, leaves `state.SCANNING` false and lets the framework produce the error response after reconciliation has already mutated the registry.
  - Does not retry failed broadcasts, return partial counts, perform authentication, read request data, append to the event log, answer gates, restart workers, contact sidecar sockets directly, or persist the fleet outside process memory.
- emits: two dashboard shell websocket broadcasts on the success path; one pre-scan broadcast before reconciliation and one post-scan broadcast after `SCANNING` is cleared. Error paths may emit no completed broadcast when the pre-scan broadcast fails, one completed pre-scan broadcast and no post-scan attempt when reconciliation fails, or one completed pre-scan broadcast plus a failed or partial post-scan attempt when the post-scan broadcast fails.
- consumes: the process-local `state.WORKFLOWS` registry, the process-local `state.SCANNING` flag, Docker workflow discovery results, and the current connected dashboard websocket client set.
- code: groom/groom/app.py::refresh
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers,
  groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable
- request:
  - method: `POST`
  - path: `/refresh`
  - path variables: none
  - query: none
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200` on successful reconciliation and broadcasts.
  - media: `application/json`
  - body: object with `ok: true` and `count: int`; `count` is the number of workflows returned by the scan before any prune decision.
  - field: `ok`; type boolean; required; default none; always `true` on the successful handler return path.
  - field: `count`; type integer; required; default none; number of workflow containers returned by the discovery scan before safe pruning, not the final registry size.
  - errors: no endpoint-specific error body is produced; broadcast, reconciliation, response-construction, and request parsing failures propagate through the framework after the state effects described above.

### receive-progress-push

- on: [post-push-progress](#post-push-progress)
- trigger: a workflow container's `groom-sidecar`, or another compatible backstop client, posts progress JSON to `POST /push/progress`.
- when:
  - The groom process has started successfully and the Litestar route table includes the progress-push route.
  - The request body has been parsed as a [progress push payload](../progress-push-payload.md) JSON object and may contain sidecar identity plus a current-node snapshot.
  - No authentication, cookies, request headers, query string, or prior workflow discovery state is required by the handler.
- does:
  - Enters `groom/groom/app.py::push_progress` with the parsed request body as `data`.
  - Reads `data["container_id"]`, substitutes an empty string when absent, converts the value to `str`, and truncates the normalized id to 12 characters.
  - If the normalized id is empty, returns `200 OK` with `{"ok": false}` without resolving Docker metadata, creating or updating a workflow, or broadcasting dashboard HTML.
  - Calls the [push-first volume metadata resolver](../concepts/push-first-volume-metadata-resolver.md) for a non-empty id before applying progress fields.
  - The resolver reads the current registry entry for the id; when the entry already has `workspace_volume`, it skips Docker inspection and makes no metadata changes.
  - When the entry is absent or lacks `workspace_volume`, the resolver inspects the Docker container on a worker thread, converts the inspection result into a workflow-container view, and upserts only `workspace_volume`, `runs_volume`, and `workflow_type` from that view.
  - If Docker inspection returns no data or invalid JSON, the resolver leaves registry metadata unchanged and the progress update continues without volume metadata; unexpected inspection exceptions propagate before the progress upsert.
  - Calls the [upsert workflow](../concepts/workflow-registry.md#method-upsert-workflow) registry method for the normalized id, creating a new workflow row when absent or updating the existing row when present.
  - Passes `state=WorkflowState.RUNNING` and optional payload fields for `name`, `repo_name`, `repo_branch`, and `current_node`; the upsert applies only values that are not `None` and ignores any field name outside the workflow-container contract.
  - When no workflow row exists yet, the upsert creates a [workflow container](../concepts/workflow-container.md) keyed by the normalized id and chooses its initial display name from the non-null payload `name`, or from the first 12 characters of the normalized id when no name is supplied.
  - Leaves existing gates, exit code, workflow type, run id, workspace volume, and runs volume unchanged unless `_ensure_volumes` or the upsert call has a non-null replacement for those fields.
  - Calls `_broadcast_shell()` after the upsert, causing connected dashboard websocket clients to receive a fresh out-of-band shell fragment for the current workflow fleet; if rendering or queueing that fragment raises, the workflow mutation has already happened and the handler does not return its success body.
  - Returns `200 OK` with `{"ok": true}` after the successful broadcast.
  - Does not append to the event log, emit a browser notification script, clear operator gates, record terminal state, answer gate files, prune workflows, or run fleet discovery.
- emits: one dashboard shell websocket broadcast on the success path; no broadcast on missing/empty container id.
- consumes: [progress push payload](../progress-push-payload.md) JSON from the container sidecar/backstop, process-local workflow state, optional Docker inspection metadata resolved by the [push-first volume metadata resolver](../concepts/push-first-volume-metadata-resolver.md), and the current connected dashboard websocket client set.
- code: groom/groom/app.py::push_progress
- request:
  - method: `POST`
  - path: `/push/progress`
  - path variables: none
  - query: none
  - headers: none required by the handler.
  - body: [progress push payload](../progress-push-payload.md) JSON object with required-for-success `container_id` and optional `name`, `repo_name`, `repo_branch`, and `current_node` fields; non-object bodies do not have endpoint-specific handling because the handler contract starts from the parsed dictionary supplied by the framework.
  - field: `container_id`; type string-convertible JSON value; required for success; default `""`; converted with `str(value)[:12]` and used as the workflow registry key, with an empty normalized value producing `ok: false`.
  - field: `name`; type any JSON value accepted by workflow name assignment; required false; default omitted; non-null values update the display name, while omitted or `null` values preserve the existing name and an empty string falls back to the normalized id only when a workflow row is first created.
  - field: `repo_name`; type any JSON value accepted by workflow repository-name assignment; required false; default omitted; non-null values replace the repository name shown by the dashboard, including an empty string.
  - field: `repo_branch`; type any JSON value accepted by workflow repository-branch assignment; required false; default omitted; non-null values replace the repository branch shown by the dashboard, including an empty string.
  - field: `current_node`; type any JSON value accepted by workflow current-node assignment; required false; default omitted; non-null values replace the current workflow-node label while the workflow is marked running, including an empty string.
  - field: other JSON members; type any; required false; default omitted; ignored by this invocation and not passed to Docker metadata resolution, workflow upsert, shell rendering, broadcast, or the response body.
- response:
  - status: `200` on normal handler return.
  - media: `application/json`
  - body: object with `ok: bool`; `false` means the request lacked a usable container id, and `true` means the workflow state was updated and the shell broadcast completed.
  - field: `ok`; type boolean; required; default none; `false` only on the missing-or-empty normalized container-id path before any mutation or broadcast, and `true` only after Docker metadata resolution, workflow upsert, shell rendering, and broadcast queueing complete.
  - errors: no endpoint-specific error body is produced; Docker metadata lookup, registry upsert, shell rendering, broadcast queueing, or response construction failures propagate as framework errors.

### receive-blocked-push

- on: [post-push-blocked](#post-push-blocked)
- trigger: a workflow container's `groom-sidecar`, the await-operator backstop push, or another compatible client posts blocked-gate JSON to `POST /push/blocked`.
- when:
  - The groom process has started successfully and the Litestar route table includes the blocked-push route.
  - The request body has been parsed as a [blocked push payload](../blocked-push-payload.md) JSON object and may contain sidecar identity plus one gate file path and gate question.
  - No authentication, cookies, request headers, query string, prior workflow discovery state, or connected dashboard websocket is required by the handler.
- does:
  - Enters `groom/groom/app.py::push_blocked` with the parsed request body as `data`.
  - Reads `data["container_id"]`, substitutes an empty string when absent, converts the value to `str`, and truncates the normalized id to 12 characters.
  - Reads `data["file_path"]`, substitutes an empty string when absent, and converts the value to `str`.
  - If the normalized id or normalized file path is empty, returns `200 OK` with `{"ok": false}` without resolving Docker metadata, creating or updating a workflow, recording a gate, rendering fragments, or broadcasting dashboard HTML.
  - Calls `_ensure_volumes(container_id)` for a valid id and path, so a push-first workflow can gain workspace and runs volume metadata from Docker inspection when that metadata is not already known.
  - Reads `data["question"]`, substitutes an empty string when absent, and converts the value to `str` for the stored gate question.
  - Calls `state.upsert_workflow` for the normalized id, creating a new workflow row when absent or updating the existing row when present.
  - Sets the workflow state to `BLOCKED` and applies non-null `name`, `repo_name`, and `repo_branch` payload values; omitted or null optional fields do not overwrite existing workflow fields.
  - Leaves current node, exit code, workflow type, run id, workspace volume, and runs volume unchanged unless `_ensure_volumes` or the upsert call has a non-null replacement for those fields.
  - Inserts or replaces `wf.gates[file_path]` with a [gate info](../concepts/gate-info.md) record carrying the normalized container id, normalized gate file path, normalized question, and default awaiting-operator status.
  - Calls the [dashboard shell renderer](../concepts/dashboard-shell-renderer.md) with the current `state.WORKFLOWS` snapshot and out-of-band mode enabled, producing a [dashboard shell fragment](../dashboard-shell-fragment.md) for the same fleet state that now includes the blocked workflow and stored gate.
  - The shell fragment contains the [operator inbox](../operator-inbox.md) live region followed by the status-bar live region; it does not include the selected worker detail pane, repository menu, Files panel, Diff panel, or browser notification script.
  - Calls the [blocked notification script renderer](../concepts/blocked-notification-script-renderer.md) with message text formed from the workflow name, a colon separator, and the first 200 characters of the question.
  - Appends the returned [blocked notification script fragment](../blocked-notification-script-fragment.md) after the shell fragment; when the dashboard executes it, it dispatches `groom:blocked` on `document.body` with the message as the CustomEvent `detail` string.
  - Calls the [dashboard client queue set](../concepts/dashboard-client-queue-set.md#method-broadcast-dashboard-fragment) with the combined shell-plus-notification fragment.
  - The broadcaster snapshots the currently registered dashboard client queues before queueing, awaits one enqueue per snapshot queue, and does not send to sidecar websockets, create clients, retry failed queues, or persist the fragment.
  - If queueing fails or is cancelled partway through, earlier queues in the snapshot may already contain the fragment; the exception propagates before this invocation returns its success body.
  - Returns `200 OK` with `{"ok": true}` after the successful broadcast.
  - Does not append to the event log, answer or write gate files, clear other open gates, record terminal state, prune workflows, contact the sidecar data-plane socket, run fleet discovery, or retry notification delivery.
- emits: one dashboard shell websocket broadcast plus one [blocked notification script fragment](../blocked-notification-script-fragment.md) on the success path; no broadcast on missing/empty container id or missing/empty gate file path.
- consumes: [blocked push payload](../blocked-push-payload.md) JSON from the container sidecar/backstop, process-local workflow state, optional Docker inspection metadata, and the current [dashboard client queue set](../concepts/dashboard-client-queue-set.md).
- code: groom/groom/app.py::push_blocked
- request:
  - method: `POST`
  - path: `/push/blocked`
  - path variables: none
  - query: none
  - headers: none required by the handler.
  - body: [blocked push payload](../blocked-push-payload.md) JSON object with required-for-success `container_id` and `file_path` fields plus optional `question`, `name`, `repo_name`, and `repo_branch` fields; non-object bodies do not have endpoint-specific handling because the handler contract starts from the parsed dictionary supplied by the framework.
  - field: `container_id`; type string-convertible JSON value; required for success; default `""`; converted with `str(value)[:12]` and used as the workflow registry key, with an empty normalized value producing `ok: false` before any mutation or broadcast.
  - field: `file_path`; type string-convertible JSON value; required for success; default `""`; converted with `str(value)` and used as the key in the workflow's gate map, with an empty normalized value producing `ok: false` before any mutation or broadcast.
  - field: `question`; type string-convertible JSON value; required false; default `""`; converted with `str(value)`, stored unchanged on the gate record, and truncated only when forming the browser notification message.
  - field: `name`; type any JSON value accepted by workflow name assignment; required false; default omitted; non-null values update the display name, while omitted or `null` values preserve the existing name and an empty string falls back to the normalized id only when a workflow row is first created.
  - field: `repo_name`; type any JSON value accepted by workflow repository-name assignment; required false; default omitted; non-null values replace the repository name shown by the dashboard, including an empty string.
  - field: `repo_branch`; type any JSON value accepted by workflow repository-branch assignment; required false; default omitted; non-null values replace the repository branch shown by the dashboard, including an empty string.
  - field: other JSON members; type any; required false; default omitted; ignored by this invocation and not passed to Docker metadata resolution, workflow upsert, gate storage, shell rendering, notification rendering, broadcast, or the response body.
- response:
  - status: `200` on normal handler return.
  - media: `application/json`
  - body: object with `ok: bool`; `false` means the request lacked a usable container id or gate file path, and `true` means the workflow state was marked blocked, the gate was stored, and the shell-plus-notification broadcast completed.
  - field: `ok`; type boolean; required; default none; `false` on the validation-failure path and `true` only after the dashboard broadcast has accepted the shell-plus-notification fragment.
  - errors: no endpoint-specific error body is produced; volume metadata lookup, workflow upsert, shell rendering, notification rendering, broadcast queueing, or response construction failures propagate as framework errors.

### receive-exited-push

- on: [post-push-exited](#post-push-exited)
- trigger: a workflow container entrypoint, `groom-sidecar --exit-code`, or another compatible residual client posts workflow-exited JSON to `POST /push/exited` after the workflow process has returned.
- when:
  - The groom process has started successfully and the Litestar route table includes the exited-push route.
  - The request body has been parsed as a JSON object and may contain sidecar identity plus an exit-code snapshot.
  - No authentication, cookies, request headers, query string, prior workflow discovery state, open gate, or connected dashboard websocket is required by the handler.
- does:
  - Enters `groom/groom/app.py::push_exited` with the parsed request body as `data`.
  - Reads `data["container_id"]`, substitutes an empty string when absent, converts the value to `str`, and truncates the normalized id to 12 characters.
  - If the normalized id is empty, returns `200 OK` with `{"ok": false}` without resolving Docker metadata, creating or updating a workflow, clearing gates, rendering fragments, or broadcasting dashboard HTML.
  - Calls `_ensure_volumes(container_id)` for a non-empty id, so a push-first workflow can gain workspace and runs volume metadata from Docker inspection when that metadata is not already known.
  - Reads `data["exit_code"]` without a default; when the value is an `int` or `str` whose string form is decimal digits with an optional leading `-`, converts it to `int`, otherwise uses `None`.
  - Calls `state.upsert_workflow` for the normalized id, creating a new workflow row when absent or updating the existing row when present.
  - Sets the workflow state to [workflow state](../concepts/workflow-state.md) `FINISHED`, stores the parsed exit code when numeric, and applies non-null `name`, `repo_name`, and `repo_branch` payload values; omitted, null, or non-numeric optional fields do not overwrite existing workflow fields.
  - Leaves current node, existing exit code when no numeric exit code is supplied, workflow type, run id, workspace volume, and runs volume unchanged unless `_ensure_volumes` or the upsert call has a non-null replacement for those fields.
  - Clears the workflow's `gates` mapping completely, removing every pending operator gate for the exited container.
  - Calls `_broadcast_shell()` after the update, causing connected dashboard websocket clients to receive a fresh out-of-band shell fragment for the current workflow fleet.
  - Returns `200 OK` with `{"ok": true}` after the successful broadcast.
  - Does not append to the event log, emit a browser notification script, answer or write gate files, prune workflows, contact the sidecar data-plane socket, run fleet discovery, or retry broadcast delivery.
- emits: one dashboard shell websocket broadcast on the success path; no broadcast on missing/empty container id.
- consumes: [exited push payload](../exited-push-payload.md) JSON from the container entrypoint sidecar path, process-local workflow state, optional Docker inspection metadata, and the current connected dashboard websocket client set.
- code: groom/groom/app.py::push_exited
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code,
  groom/tests/test_app.py::test_push_exited_rejects_missing_container_id
- request:
  - method: `POST`
  - path: `/push/exited`
  - path variables: none
  - query: none
  - headers: none required by the handler.
  - body: [exited push payload](../exited-push-payload.md) JSON object with required-for-success `container_id` plus optional `exit_code`, `name`, `repo_name`, and `repo_branch` fields.
  - field: `container_id`; type string-convertible JSON value; required for success; default `""`; converted with `str(value)[:12]` and used as the workflow registry key, with an empty normalized value producing `ok: false` before volume resolution, registry mutation, gate clearing, or broadcast.
  - field: `exit_code`; type integer or string containing decimal digits with an optional leading `-`; required false; default omitted; converted to `int` and written to the workflow only when the type and numeric-shape check passes. Non-numeric strings, values with `+` signs or surrounding whitespace, floats, booleans, null, objects, arrays, and omitted values are treated as absent and preserve any existing workflow exit code.
  - field: `name`; type any JSON value accepted by workflow name assignment; required false; default omitted; non-null values update the display name, while omitted or `null` values preserve the existing name and an empty string falls back to the normalized id only when a workflow row is first created.
  - field: `repo_name`; type any JSON value accepted by workflow repository-name assignment; required false; default omitted; non-null values replace the repository name shown by the dashboard, including an empty string.
  - field: `repo_branch`; type any JSON value accepted by workflow repository-branch assignment; required false; default omitted; non-null values replace the repository branch shown by the dashboard, including an empty string.
  - field: other JSON members; type any; required false; default omitted; ignored by this invocation and not passed to Docker metadata resolution, workflow upsert, gate clearing, shell rendering, broadcast, or the response body.
- response:
  - status: `200` on normal handler return.
  - media: `application/json`
  - body: object with `ok: bool`; `false` means the request lacked a usable container id, and `true` means the workflow state was marked finished, open gates were cleared, and the shell broadcast completed.
  - field: `ok`; type boolean; required; default none; `false` on the validation-failure path and `true` only after `_ensure_volumes`, `state.upsert_workflow`, gate clearing, and `_broadcast_shell` complete.
  - errors: no endpoint-specific error body is produced; volume metadata lookup, workflow upsert, shell rendering, broadcast queueing, or response construction failures propagate as framework errors.

### reload-sidecars

- on: [post-reload](#post-reload)
- trigger: a developer tool, dashboard control, or compatible HTTP client posts to `POST /reload`, optionally with `container_id` to constrain the reload to one connected workflow container.
- when:
  - The groom process has started successfully and the Litestar route table includes the reload route.
  - `container_id` may be empty, a known connected sidecar id, or an id with no current sidecar connection.
  - No authentication, cookies, request headers, request body, workflow discovery state, browser websocket, or Docker availability is required by the handler.
- does:
  - Enters `groom/groom/app.py::reload` with `container_id` parsed from the query string and defaulted to `""` when omitted.
  - If `container_id` is non-empty, builds a single-target list containing that value exactly as parsed, without applying the 12-character container-id truncation used by sidecar registration and push endpoints.
  - If `container_id` is empty, asks the process-local [sidecar connection registry](../concepts/sidecar-connection-registry.md) for the current connected sidecar ids through `connected_ids()` and uses that snapshot as the fixed target list for this request.
  - Initializes `reloaded` to `0` before sending any commands.
  - For each target id, looks up the registered [sidecar connection](../concepts/sidecar-connection.md) through `get(container_id)`; missing connections are skipped without changing the count, which allows an all-sidecars snapshot entry to disappear before its turn.
  - For each live connection, calls `send_reload()`, producing the serialized `{"type":"reload"}` outbound websocket frame described by [websocket-sidecar](#websocket-sidecar).
  - Increments `reloaded` after a target connection accepts the reload command.
  - Swallows exceptions from a target send so a dead socket prevents only that target's count increment, leaves registry cleanup to the websocket session lifecycle, does not fail the HTTP request, and does not stop later targets.
  - Returns `200 OK` with JSON `{"ok": true, "reloaded": reloaded}` after every target has been attempted.
  - Does not mutate workflow state, clear gates, broadcast dashboard shell fragments, inspect Docker, read workspace files, schedule discovery, wait for sidecars to disconnect, wait for sidecars to reconnect, or verify that the container actually restarted.
- emits: zero or more sidecar websocket reload frames, one per targeted live connection whose send succeeds; no browser websocket broadcast and no process-local workflow state change.
- consumes: the process-local sidecar connection registry and the optional `container_id` query string.
- code: groom/groom/app.py::reload
- verify: groom/tests/test_app.py::test_reload_broadcasts_to_all_connected_sidecars,
  groom/tests/test_app.py::test_reload_targets_one_container_when_id_given
- request:
  - method: `POST`
  - path: `/reload`
  - path variables: none
  - query: `container_id` string, optional, default `""`; empty targets the current registry snapshot, non-empty targets exactly that id.
  - headers: none required by the handler.
  - body: none
- response:
  - status: `200` on normal handler return.
  - media: `application/json`
  - body: object with `ok: true` and integer `reloaded` count of successful reload sends.
  - field: `ok`; type boolean; required; default none; always `true` on the handler's normal return path.
  - field: `reloaded`; type integer; required; default none; starts at `0` and increments once for each target connection whose `send_reload()` call completes.
  - errors: no endpoint-specific error body is produced; missing target connections and send exceptions are swallowed per target, while request parsing or response construction failures are framework-level failures.

### serve-static-asset

- on: [get-static-assets](#get-static-assets)
- trigger: a browser dashboard tab or another HTTP client requests one packaged asset below `/assets/`.
- when:
  - The groom process has started successfully from the Litestar application returned by `create_app`.
  - The application route table includes the static-files router mounted at `/assets`.
  - The requested path is interpreted inside the packaged `groom/groom/assets` directory.
  - No authentication, cookies, request body, query string, workflow discovery state, browser websocket, or sidecar websocket is required by groom.
- does:
  - Enters the route table that `groom/groom/app.py::create_app` built for `/assets`.
  - Uses the static-files router that `create_app` constructed with `path="/assets"` and the package asset directory [field-assets-dir](../concepts/groom-app-module.md#field-assets-dir).
  - Exposes only the packaged dashboard asset files present under `groom/groom/assets`: `htmx.min.js`, `htmx-ext-ws.min.js`, `diff2html.min.js`, `diff2html.min.css`, `marked.min.js`, `purify.min.js`, `highlight.min.js`, `hljs-github-dark.min.css`, and `dashboard.css`.
  - Delegates per-request path validation, file lookup, conditional request handling, media-type selection, and static response construction to the mounted framework static-file router; no first-party route handler function runs for an individual asset request.
  - Returns the matched packaged asset bytes when the requested asset exists.
  - Lets the static-file router produce missing-file, unsupported-method, and conditional-request responses for paths it cannot serve as a normal asset body.
  - Leaves process-local workflow state, sidecar registrations, dashboard websocket clients, discovery scans, and event logs unchanged.
  - Does not fetch third-party CDN resources, transform asset bytes, render templates, or emit websocket/browser-push updates.
- emits: one HTTP static-file response only; no browser websocket broadcast and no sidecar websocket frame.
- consumes: the package asset directory rooted at `groom/groom/assets` through `ASSETS_DIR`, including the vendored JavaScript, CSS, diff-rendering, markdown, sanitization, syntax-highlight, and dashboard stylesheet assets used by the dashboard shell; no workflow, sidecar, Docker, or request-body data.
- code: groom/groom/app.py::create_app
- request:
  - method: `GET`
  - path: `/assets/{path...}` where `{path...}` is required and relative to `groom/groom/assets`.
  - path variable: `path` string, required, no default; selects one packaged asset below [field-assets-dir](../concepts/groom-app-module.md#field-assets-dir).
  - query: none consumed by groom.
  - headers: none required by groom; conditional headers and cache validators are static-router behavior when supported.
  - body: none
- response:
  - status: `200` when the path maps to an existing packaged asset; otherwise the framework static-file status.
  - media: static-file media type for the requested asset.
  - body: raw packaged asset bytes, with no groom-specific envelope.
  - errors: no endpoint-specific error body is produced by groom; missing files, unsupported methods, invalid paths, and conditional request outcomes are handled by the mounted static-file router.

### run-dashboard-websocket-session

- on: [websocket-dashboard](#websocket-dashboard)
- trigger: a browser tab running the [groom dashboard](../gui/screens/groom-dashboard.md) opens the htmx websocket extension connection to `WS /ws`, or submits a dashboard `ws-send` answer form over that open connection.
- when:
  - The groom process has started successfully and the Litestar route table includes the `/ws` websocket route.
  - The dashboard client can complete a websocket upgrade to the same origin serving the dashboard shell.
  - The process-local workflow registry may be empty, scanning, running, blocked, or finished; no Docker or sidecar availability is required to open the socket.
  - Answer-command handling requires a JSON frame with `cmd` equal to `"answer"`; missing or unknown commands are ignored.
- does:
  - Enters `groom/groom/app.py::dashboard_ws` with the accepted browser websocket object.
  - Accepts the websocket and creates one unbounded in-process queue for outbound dashboard fragments for this client.
  - Registers the queue through the [dashboard client queue set](../concepts/dashboard-client-queue-set.md#method-register-dashboard-client) before rendering the initial frame; registration inserts that exact queue object into the process-local client set, is idempotent for the same queue object, and makes subsequent `state.broadcast(...)` calls target this tab.
  - Reads the current workflow registry through `_all_workflows()` and immediately sends `render.render_shell_data(workflows, oob=True)` as an HTML text frame; this initial send is direct to the accepted socket and does not pass through the per-client queue.
  - Starts the [dashboard websocket send loop](../concepts/dashboard-websocket-send-loop.md) as the outbound loop for this tab; it waits indefinitely on this tab's registered queue, preserves queue order, and sends each queued HTML/script fragment as one websocket text frame without rendering, validation, acknowledgement, retry, or additional broadcast.
  - Starts the [dashboard websocket receive loop](../concepts/dashboard-websocket-receive-loop.md) as the inbound loop for this tab; it waits indefinitely for decoded JSON frames from the accepted browser websocket and passes each frame unchanged to `_handle_command`.
  - The receive loop serializes inbound handling per websocket session by awaiting `_handle_command` before receiving the next frame; it performs no command filtering, field normalization, schema validation, logging, state mutation, response-frame send, or dashboard broadcast itself.
  - For an inbound object whose `cmd` is not `"answer"`, `_handle_command` returns without changing workflow state, writing gate files, recording log entries, or broadcasting.
  - For an answer command, `_handle_command` consumes a [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md), string-normalizes `workflow_id`, `file_path`, and `answer`, looks up the workflow's current workspace volume when known, and calls `answer_gate(container_id, file_path, answer, workspace_volume=...)`.
  - Receives an [answer result](../answer-result.md) from the gate-answering layer and records one [answer log entry](../answer-log-entry.md) for every attempted answer with event `answer`, the container id, gate file path, result `ok` flag, and result message.
  - When the answer succeeds and the workflow has no remaining gates while its visible state is `BLOCKED`, changes that workflow state to `RUNNING` immediately.
  - Broadcasts a fresh out-of-band dashboard shell after every attempted answer so all connected tabs converge on the current fleet and gate state.
  - Adds a `groom:answered` dashboard script to the broadcast only when `answer_gate` reports success; failures broadcast the shell without the answered event.
  - Waits until either send or receive loop completes, cancels the still-pending loop, treats a `WebSocketDisconnect` exception from the completed loop as normal session termination, and propagates any other completed-loop exception.
  - Always removes the queue from the global client set through [unregister dashboard client](../concepts/dashboard-client-queue-set.md#method-unregister-dashboard-client) in the cleanup path, including failures during initial rendering/sending, loop startup, loop execution, answer handling, or exception propagation. Removal discards only this tab's queue, tolerates an already-absent queue, leaves any queued fragments and websocket transport cleanup to the session tasks/framework, and prevents later broadcast snapshots from targeting this queue.
- emits: an initial dashboard shell websocket text frame for the connecting tab; later dashboard shell broadcasts and optional `groom:answered` scripts to connected dashboard tabs after answer attempts.
- consumes: process-local workflow state, process-local dashboard client queues consumed by the [dashboard websocket send loop](../concepts/dashboard-websocket-send-loop.md), inbound frames consumed by the [dashboard websocket receive loop](../concepts/dashboard-websocket-receive-loop.md), [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) messages, and [answer result](../answer-result.md) values from the gate-answering layer.
- code: groom/groom/app.py::dashboard_ws
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script,
  groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch,
  groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- request:
  - method: websocket upgrade
  - path: `/ws`
  - path variables: none
  - query: none
  - headers: no endpoint-specific headers beyond the websocket upgrade handshake.
  - body: none before websocket accept; after accept, browser text frames are decoded as JSON and passed to the receive loop.
  - inbound-frame: [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) JSON object for answer submissions; other decoded JSON values may arrive but only object frames with command fields used by `_handle_command` can produce effects.
  - field: `cmd`; type string; required for action; default absent; only `"answer"` triggers answer handling, and every other value is ignored.
  - field: `workflow_id`; type string-convertible value; required for a meaningful answer attempt; default `""`; normalized with `str(...)` before workflow lookup and gate answering.
  - field: `file_path`; type string-convertible value; required for a meaningful answer attempt; default `""`; normalized with `str(...)` and used as the gate-file key.
  - field: `answer`; type string-convertible value; optional; default `""`; normalized with `str(...)` and passed as the operator answer text.
- response:
  - status: accepted websocket connection on normal route start.
  - media: websocket text frames containing HTML fragments or dashboard event scripts.
  - initial-frame: one out-of-band [dashboard shell fragment](../dashboard-shell-fragment.md) rendered from the current process-local workflow registry and sent directly to the connecting tab immediately after registration.
  - queued-frame: zero or more later text frames, each exactly one HTML/script fragment dequeued from this tab's registered dashboard client queue by the send loop.
  - command-response: no per-command acknowledgement frame; answer attempts are reflected by a broadcast shell update to all currently registered dashboard clients, with a `groom:answered` script appended only for successful answers.
  - errors: ordinary websocket disconnect from the completed send or receive loop ends the session normally; non-disconnect loop exceptions, initial-render failures, send failures, malformed receive frames, and answer-handler failures propagate through the framework after cleanup rather than producing an endpoint-specific error payload.

### run-sidecar-websocket-session

- on: [websocket-sidecar](#websocket-sidecar)
- trigger: a `groom-sidecar` process running inside a workflow container opens `WS /sidecar` on the groom server, reconnects after a dropped session, streams a progress or blocked event, or returns one RPC result over the connected socket.
- when:
  - The groom process has started successfully and the Litestar route table includes the `/sidecar` websocket route.
  - The client can complete a websocket upgrade to the groom host/port configured for sidecars.
  - A sidecar session is usable only after a `hello` frame supplies a non-empty `identity.container_id`; frames before that useful hello are ignored except for another hello attempt.
  - The process-local workflow registry may be empty, partially discovered, populated from residual push endpoints, or carrying stale gates from an earlier session; `hello` is authoritative for the connected container's current gates.
- does:
  - Enters `groom/groom/app.py::dashboard_sidecar` with the accepted sidecar websocket object and the [sidecar websocket frame](../sidecar-websocket-frame.md) contract as its inbound message schema.
  - Accepts the websocket and initializes the session without a registered connection.
  - Receives JSON frames in a loop and ignores frames that do not decode to a JSON object.
  - For a `hello` frame, reads `identity.container_id`, substitutes an empty string when absent, converts it to `str`, truncates it to 12 characters, and ignores the frame if the normalized id is empty.
  - For a useful `hello`, constructs a [sidecar connection](../concepts/sidecar-connection.md) for that container id and socket; the connection starts with an empty pending-RPC map, a correlation counter at `0`, and a send lock used by later host-issued RPC and reload frames.
  - Registers the new connection in the host-side [sidecar connection registry](../concepts/sidecar-connection-registry.md) through [register](../concepts/sidecar-connection-registry.md#method-register); registration looks up the current connection for the normalized container id, fails a different stale connection's pending RPCs with `superseded by a new sidecar connection`, then stores the new connection as current for that id.
  - Applies the useful hello through the [sidecar hello applier](../concepts/sidecar-hello-applier.md).
  - The applier resolves Docker volume metadata when possible before applying the hello-specific identity fields, so later repository, file, diff, and gate-answer paths can use volume names when inspection succeeds.
  - The applier upserts the workflow identity fields `name`, `repo_name`, and `repo_branch`, preserving each existing field when the hello omits it or supplies `null`.
  - The applier preserves an existing current node unless `snapshot.current_node` is truthy, then clears the workflow's current gate map before applying the hello snapshot.
  - For each `snapshot.gates[]` entry with a non-empty string-normalized `file_path`, the applier creates one [gate info](../concepts/gate-info.md) record keyed by that file path, with the connected container id as `workflow_id` and the string-normalized `question` value as operator prompt text.
  - The applier marks truthy `snapshot.terminal` values as `FINISHED`; when not terminal, it marks the workflow `BLOCKED` if rebuilt gates exist or `RUNNING` if none do.
  - The applier broadcasts the dashboard shell after mutation and emits no per-hello acknowledgement frame, blocked-notification script, gate-file write, RPC resolution, or sidecar reload frame.
  - Ignores all non-hello frames until the connection object exists, so unauthenticated deltas cannot create workflow state without a sidecar identity.
  - For `rpc_result`, calls [resolve](../concepts/sidecar-connection.md#method-resolve) on the registered connection using string-normalized `id`, boolean-normalized `ok`, raw `data`, and string-normalized `error`; successful results complete the waiting caller with `data`, failed results complete it with [sidecar error](../concepts/sidecar-error.md), and unknown, late, duplicate, or already-completed ids are ignored by the connection.
  - For `progress`, delegates to the [sidecar progress applier](../concepts/sidecar-progress-applier.md) with the connected container id and decoded frame.
  - The progress applier upserts the connected workflow as `RUNNING`, creates a placeholder workflow named from the normalized id if the entry is somehow absent after hello establishment, applies any non-`None` `current_node` value from the frame, preserves the existing current node when the frame omits `current_node` or supplies `null`, preserves existing gate records, and broadcasts the dashboard shell after the registry update.
  - For `blocked`, delegates to the [sidecar blocked applier](../concepts/sidecar-blocked-applier.md) with the connected container id and decoded frame.
  - The blocked applier reads and string-normalizes `file_path`; an empty path returns without mutating workflow state, creating a gate, rendering, broadcasting, or notifying.
  - For a non-empty blocked path, the applier upserts the workflow as `BLOCKED`, stores or replaces one [gate info](../concepts/gate-info.md) record with the connected container id, normalized file path, and normalized question string, preserves other open gates, renders the dashboard shell, appends the blocked notification script whose text is the workflow display name plus the first 200 characters of the question, and broadcasts the combined HTML payload to dashboard browser clients.
  - Ignores any other `type` value after connection establishment without mutating workflow state, resolving RPCs, registering connections, or broadcasting.
  - Treats an ordinary websocket disconnect as a normal end-of-session condition; non-disconnect exceptions still run cleanup and then propagate through the framework.
  - In cleanup, when a sidecar connection was established, calls [unregister](../concepts/sidecar-connection-registry.md#method-unregister) on that connection.
  - Unregistering reads the current registry entry for the connection's container id, removes the entry only when it is still the same connection object, and leaves a newer reconnect registered when this cleanup belongs to a superseded socket.
  - Unregistering then fails every unresolved RPC future still pending on the closing connection with `sidecar connection closed`, even when the registry removal branch did not remove anything, so HTTP file/diff callers can fall back instead of waiting for their RPC timeout.
  - Does not authenticate sidecars, answer gate files, clear gates on disconnect, delete workflow rows when a socket closes, run fleet discovery, read workspace files itself, compute diffs itself, or send per-delta acknowledgement frames.
- emits: one dashboard shell websocket broadcast for every useful `hello`, `progress`, and non-empty-path `blocked` frame; a blocked notification script for every non-empty-path `blocked` frame; host-to-sidecar RPC and reload frames only when other server handlers use the registered connection.
- consumes: [sidecar websocket frame](../sidecar-websocket-frame.md) JSON messages for `hello`, `rpc_result`, `progress`, and `blocked`; process-local workflow state; optional Docker inspection metadata resolved by `_ensure_volumes`; the process-local [sidecar connection registry](../concepts/sidecar-connection-registry.md); the [sidecar blocked applier](../concepts/sidecar-blocked-applier.md); and the current connected dashboard websocket client set.
- code: groom/groom/app.py::dashboard_sidecar
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate,
  groom/tests/test_app.py::test_apply_hello_running_when_no_gates,
  groom/tests/test_app.py::test_apply_hello_finished_when_terminal,
  groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively,
  groom/tests/test_sidecar_hub.py::test_rpc_sends_request_and_returns_resolved_data,
  groom/tests/test_sidecar_hub.py::test_resolve_is_ignored_after_timeout,
  groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection
- request:
  - method: websocket upgrade
  - path: `/sidecar`
  - path variables: none
  - query: none
  - headers: no endpoint-specific headers beyond the websocket upgrade handshake.
  - body: none before websocket accept; after accept, the request stream is websocket JSON frames matching [sidecar websocket frame](../sidecar-websocket-frame.md).
  - inbound-frame: top-level JSON values are received one at a time; non-object values are ignored with no connection registration, workflow mutation, RPC resolution, dashboard broadcast, sidecar reply frame, or error frame.
  - field: `type`; type string; required for action; default absent; `hello` can establish identity, `rpc_result` can resolve a pending host-issued RPC after identity is established, `progress` can mark live running progress after identity is established, `blocked` can record one live gate after identity is established, and every other value is ignored.
  - field: `identity`; type object; required for useful `hello`; default `{}`; carries the sidecar identity object used only by the hello path.
  - field: `identity.container_id`; type string-convertible JSON value; required for sidecar registration; default `""`; normalized with `str(value)[:12]`, and an empty normalized value makes the hello frame ineffective.
  - field: `identity.name`; type any JSON value accepted by workflow display-name assignment; required false; default omitted; non-null values update the workflow name through the hello applier.
  - field: `identity.repo_name`; type any JSON value accepted by workflow repository-name assignment; required false; default omitted; non-null values update the repository name through the hello applier.
  - field: `identity.repo_branch`; type any JSON value accepted by workflow repository-branch assignment; required false; default omitted; non-null values update the repository branch through the hello applier.
  - field: `snapshot`; type object; required false for `hello`; default `{}`; contains the sidecar's authoritative reconnect snapshot for current node, terminal state, and open gates.
  - field: `snapshot.current_node`; type any JSON value; required false; default omitted; truthy values replace the workflow current-node field through the hello applier, while falsey or absent values preserve it.
  - field: `snapshot.terminal`; type truthy/falsy JSON value; required false; default falsey; truthy values mark the workflow finished through the hello applier.
  - field: `snapshot.gates`; type array of objects; required false; default `[]`; hello clears the workflow's existing gate map before retaining entries from this list.
  - field: `snapshot.gates[].file_path`; type string-convertible JSON value; required for a retained snapshot gate; default `""`; empty normalized values are skipped.
  - field: `snapshot.gates[].question`; type string-convertible JSON value; required false; default `""`; stored on retained snapshot gate records.
  - field: `id`; type string-convertible JSON value; required for useful `rpc_result`; default `""`; correlation id of a pending host-issued sidecar RPC on the registered connection.
  - field: `ok`; type truthy/falsy JSON value; required false for `rpc_result`; default false; truthy values deliver `data` to the pending caller and falsey values deliver a sidecar error.
  - field: `data`; type any JSON value; required false; default `null`; successful RPC result payload delivered unchanged to the pending HTTP data-plane caller.
  - field: `error`; type string-convertible JSON value; required false; default `""`; failure message for a falsey `rpc_result`.
  - field: `current_node`; type any JSON value; required false for `progress`; default omitted; non-`None` values update the workflow current-node field while marking the workflow running.
  - field: `file_path`; type string-convertible JSON value; required for useful `blocked`; default `""`; empty normalized values make the blocked frame a no-op.
  - field: `question`; type string-convertible JSON value; required false for `blocked`; default `""`; stored on the live gate record and truncated only for the browser notification preview.
  - field: other JSON members; type any; required false; default omitted; ignored by this invocation unless a delegated applier or pending RPC caller consumes them through the documented frame shape.
- response:
  - status: accepted websocket connection on normal route start.
  - media: websocket JSON text frames for host-issued RPC and reload messages.
  - body: no HTTP response body after the websocket upgrade; session effects are represented as websocket frames, dashboard broadcasts, and pending in-process RPC future resolution.
  - outbound-frame: `{"type":"rpc","id":string,"method":"getTree","params":{"repo":string}}` may be sent later by the [get-workspace-file-list](#get-workspace-file-list) invocation through the registered [sidecar connection](../concepts/sidecar-connection.md) for this container.
  - outbound-frame: `{"type":"rpc","id":string,"method":"getFile","params":{"repo":string,"path":string}}` may be sent later by the [get-workspace-file-content](#get-workspace-file-content) invocation through the registered sidecar connection for this container.
  - outbound-frame: `{"type":"rpc","id":string,"method":"getDiff","params":{"repo":string}}` may be sent later by the [get-workspace-diff](#get-workspace-diff) invocation through the registered sidecar connection for this container.
  - outbound-frame: `{"type":"reload"}` may be sent later by the [reload-sidecars](#reload-sidecars) invocation through the registered sidecar connection for this container.
  - command-response: no acknowledgement frame is sent for `hello`, `progress`, or `blocked`; successful effects are visible only through browser dashboard websocket broadcasts.
  - rpc-result-response: no websocket reply is sent for `rpc_result`; a matching pending in-process future is resolved or failed, and unknown, late, duplicate, or already-completed ids are ignored.
  - cleanup-result: ordinary websocket disconnect ends the session without an endpoint payload; if a connection was established, cleanup unregisters this connection only when it is still current and fails its unresolved RPC futures with `sidecar connection closed`.
  - errors: malformed JSON frames, receive failures other than ordinary websocket disconnect, send failures from later host-issued RPC or reload frames, connection-registration failures, delegated applier failures, renderer failures, broadcast failures, and cleanup-time failures are not converted into sidecar protocol error frames; they propagate through the websocket handler or through the waiting HTTP caller after cleanup semantics run where applicable.
