---
type: concept
slug: groom-sidecar-module
title: Groom sidecar module
---
# Groom sidecar module

The Groom sidecar module is the in-container runtime implementation behind the
[`groom-sidecar`](../groom-sidecar.md) command. It owns the sidecar process'
import-time configuration, local snapshot readers, residual HTTP push producers,
recursive inotify-backed websocket session, sidecar-local RPC data plane, reload
control signal, and the blocking handoff from the CLI into [sidecar live
sessions](../sidecar-live-sessions.md). The module exchanges [sidecar identity
data](../sidecar-identity-data.md), [sidecar snapshot data](../sidecar-snapshot-data.md),
[sidecar websocket frame](../sidecar-websocket-frame.md), [progress push
payload](../progress-push-payload.md), [blocked push payload](../blocked-push-payload.md),
[exited push payload](../exited-push-payload.md), [workspace file list
data](../workspace-file-list-data.md), [workspace file content
data](../workspace-file-content-data.md), and [workspace diff data](../workspace-diff-data.md)
without owning host workflow registry state or deciding the workflow process'
exit result.

- code: groom/groom/sidecar.py
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates,
  groom/tests/test_sidecar.py::test_push_progress_posts_expected_shape,
  groom/tests/test_sidecar.py::test_push_blocked_posts_expected_shape,
  groom/tests/test_sidecar.py::test_push_exited_posts_expected_shape,
  groom/tests/test_sidecar_session.py::test_handle_rpc_get_tree_replies_ok,
  groom/tests/test_sidecar_session.py::test_run_session_advertises_hello_then_reload_raises,
  groom/tests/test_sidecar_session.py::test_serve_returns_reload_code_when_session_requests_reload,
  groom/tests/test_sidecar_session.py::test_run_maps_reload_code_to_systemexit
- refs: [`groom-sidecar`](../groom-sidecar.md), [sidecar live sessions](../sidecar-live-sessions.md), [sidecar protocol](../sidecar-protocol.md), [websocket-sidecar](../http/groom.md#websocket-sidecar)

## Contract

- role: in-container sidecar runtime module for one workflow container.
- process boundary: runs as its own OS process through the `groom-sidecar`
  executable; it is not embedded in workhorse and does not share the host groom
  process event loop.
- authority: observes local workspace/run mounts, advertises current state, and
  serves local read-only data-plane requests; it does not decide workhorse exit
  status, mutate host workflow registry state directly, answer gates, or write
  workspace files.
- primary transport: opens an outbound websocket client connection to the host
  groom service at `WS /sidecar`, sends a full `hello` state advertisement on
  every connection, streams `progress` and `blocked` deltas from filesystem
  events, handles host-issued `rpc` frames, and exits with the reload status only
  after a host `reload` frame.
- residual transport: exposes fire-and-forget HTTP push wrappers for progress,
  blocked, and exited notices; the live websocket is primary, while residual HTTP
  remains for the post-workflow exit notice and backstop paths described by the
  sidecar protocol.
- local data plane: answers `getTree`, `getFile`, and `getDiff` RPC methods from
  the sidecar's own mounted workspace; file-content requests use the sidecar
  local relative path guard, tree reads prune heavy directories, and diffs are
  best-effort working-tree-vs-HEAD output.
- snapshot model: state is ephemeral and non-authoritative. A reconnect sends a
  fresh snapshot so dropped sockets, host restarts, and container recreation are
  reconciled from current local files instead of persisted sidecar state.
- import behavior: environment-backed constants are read when the module imports;
  later environment changes do not affect an already-imported module instance
  unless the process is relaunched or tests monkeypatch the module attributes.
- failure model: local read failures generally become empty values, unavailable
  residual HTTP pushes are swallowed, RPC handler failures become failed
  `rpc_result` frames, normal websocket closure reconnects, and reload is the only
  intentional non-zero sidecar process status.
- external boundary: standard-library JSON, filesystem, socket, subprocess, and
  HTTP helpers, the inotify and websocket packages, Git, and host networking are
  below this module and are not Groom graph concepts to descend into.

## Fields

### field-workspace-dir

- type: `pathlib.Path`
- default: `/workspace`
- required: true
- code: groom/groom/sidecar.py::WORKSPACE_DIR
- meaning: local mount root for repository/workspace reads, gate scanning,
  workspace inotify watches, and sidecar RPC file-tree/file-content service.
- source: `GROOM_WORKSPACE_DIR` environment variable when present.

### field-runs-dir

- type: `pathlib.Path`
- default: `/runs`
- required: true
- code: groom/groom/sidecar.py::RUNS_DIR
- meaning: local mount root for workhorse run metadata, latest checkpoint reads,
  terminal-state reads, and run-progress inotify watches.
- source: `GROOM_RUNS_DIR` environment variable when present.

### field-groom-host

- type: `str`
- default: `host.docker.internal`
- required: true
- code: groom/groom/sidecar.py::GROOM_HOST
- meaning: host name used for both residual HTTP pushes and the persistent
  websocket client connection back to groom.
- source: `GROOM_HOST` environment variable when present.

### field-groom-port

- type: `str`
- default: `8787`
- required: true
- code: groom/groom/sidecar.py::GROOM_PORT
- meaning: TCP port text used in the residual HTTP URL and websocket URL.
- source: `GROOM_PORT` environment variable when present.

### field-push-timeout

- type: `float` seconds
- default: `1.0`
- required: true
- code: groom/groom/sidecar.py::PUSH_TIMEOUT
- meaning: maximum duration passed to one residual HTTP push attempt before the
  HTTP helper raises into the module's fire-and-forget suppression boundary.
- source: `GROOM_PUSH_TIMEOUT` environment variable parsed as a float at import.

### field-reload-exit-code

- type: `int`
- default: `3`
- required: true
- code: groom/groom/sidecar.py::RELOAD_EXIT_CODE
- meaning: reserved sidecar process status used to ask the container entrypoint to
  recopy edited sidecar source and relaunch the sidecar after a host reload frame.
- used-by: [sidecar serving loop](sidecar-serving-loop.md) and [sidecar live
  session runner](sidecar-live-session-runner.md).

### field-watch-flags

- type: inotify mask
- default: `MODIFY | CLOSE_WRITE | CREATE | MOVED_TO`
- required: true
- code: groom/groom/sidecar.py::_WATCH_FLAGS
- meaning: filesystem event classes observed for workspace gate changes, run
  progress writes, and newly-created or moved-in directories that need watches.

### field-skip-dir-names

- type: `set[str]`
- default: `{ ".git", "node_modules", "__pycache__", ".venv" }`
- required: true
- code: groom/groom/sidecar.py::_SKIP_DIR_NAMES
- meaning: heavy or irrelevant directory names pruned by snapshot gate scans,
  recursive watch installation, and workspace file-tree RPC listing.

### field-gate-scan-head

- type: `int` characters
- default: `512`
- required: true
- code: groom/groom/sidecar.py::_GATE_SCAN_HEAD
- meaning: prefix length read from each candidate workspace file before deciding
  whether the full file must be read as an awaiting operator gate.

### field-rpc-methods

- type: `dict[str, callable]`
- default: `{ "getTree": _rpc_get_tree, "getFile": _rpc_get_file, "getDiff": _rpc_get_diff }`
- required: true
- code: groom/groom/sidecar.py::_RPC_METHODS
- meaning: first-party sidecar data-plane dispatch table for host-issued RPC
  method names.

## Public Members

### method-push-progress

- sig: `push_progress(current_node: str = "") -> None`
- abstract: false
- raises: same producer-side propagation boundary as [method-_push](sidecar-residual-http-push-helper.md#method-_push); residual HTTP open and close failures are swallowed by the helper.
- code: groom/groom/sidecar.py::push_progress
- verify: groom/tests/test_sidecar.py::test_push_progress_posts_expected_shape
- refs: [sidecar residual HTTP push helper](sidecar-residual-http-push-helper.md#method-push-progress), [progress push payload](../progress-push-payload.md)
- input: current workhorse graph-node id or `""` when no current node is known.
- output: returns `None` after delegating the one-shot push attempt.
- does:
  - Builds a progress event payload with only the `current_node` key.
  - Delegates to the residual HTTP push helper with route path `/push/progress`.
  - Does not read checkpoint files, open a websocket, install watches, mutate
    workflow state, or report delivery success to the caller.

### method-push-blocked

- sig: `push_blocked(file_path: str, question: str) -> None`
- abstract: false
- raises: same producer-side propagation boundary as [method-_push](sidecar-residual-http-push-helper.md#method-_push); residual HTTP open and close failures are swallowed by the helper.
- code: groom/groom/sidecar.py::push_blocked
- verify: groom/tests/test_sidecar.py::test_push_blocked_posts_expected_shape
- refs: [sidecar residual HTTP push helper](sidecar-residual-http-push-helper.md#method-push-blocked), [blocked push payload](../blocked-push-payload.md)
- input-file-path: workspace-relative awaiting gate file path or the observed path
  fallback supplied by an event classifier.
- input-question: operator-facing question text extracted from the gate context
  file.
- output: returns `None` after delegating the one-shot push attempt.
- does:
  - Builds a blocked event payload with `file_path` and `question` keys.
  - Delegates to the residual HTTP push helper with route path `/push/blocked`.
  - Does not classify the gate file itself, open a websocket, mutate workflow
    state, or report delivery success to the caller.

### method-push-exited

- sig: `push_exited(exit_code: int) -> None`
- abstract: false
- raises: same producer-side propagation boundary as [method-_push](sidecar-residual-http-push-helper.md#method-_push); residual HTTP open and close failures are swallowed by the helper.
- code: groom/groom/sidecar.py::push_exited
- verify: groom/tests/test_sidecar.py::test_push_exited_posts_expected_shape
- verify: groom/tests/test_sidecar.py::test_push_exited_is_silent_when_groom_is_unreachable
- refs: [sidecar residual HTTP push helper](sidecar-residual-http-push-helper.md#method-push-exited), [exited push payload](../exited-push-payload.md)
- input: integer exit code returned by the workflow process after workhorse exits.
- output: returns `None` after delegating the one-shot push attempt.
- does:
  - Builds an exited event payload with only the `exit_code` key.
  - Delegates to the residual HTTP push helper with route path `/push/exited`.
  - Does not inspect workhorse, alter the supplied exit code, open a websocket, or
    change the workflow process result.

### method-scan-gates

- sig: `scan_gates() -> list[dict]`
- abstract: false
- raises: none for a missing workspace mount or per-file read failures; those
  cases return an empty list or skip the unreadable file.
- code: groom/groom/sidecar.py::scan_gates
- verify: groom/tests/test_sidecar.py::test_scan_gates_finds_awaiting_and_skips_git_and_non_awaiting
- detail: [sidecar snapshot](sidecar-snapshot.md#method-scan_gates)
- refs: [operator gate context file](../operator-gate-context-file.md), [sidecar snapshot data](../sidecar-snapshot-data.md)
- input: no call arguments; uses [field-workspace-dir](#field-workspace-dir).
- output: list of gate entries with `file_path` and `question` keys.
- does:
  - Walks the configured workspace tree while pruning [field-skip-dir-names](#field-skip-dir-names).
  - Reads only the [field-gate-scan-head](#field-gate-scan-head) prefix of each
    candidate file before deciding whether it is awaiting operator input.
  - Reads full content only for awaiting files so the operator question can be
    extracted.
  - Returns workspace-relative file paths when possible and observed path strings
    when relativization fails.

### method-snapshot

- sig: `snapshot() -> dict`
- abstract: false
- raises: delegated reader exceptions outside their normalization contracts can
  propagate; expected missing/unreadable run and gate files become empty fields or
  skipped gate entries.
- code: groom/groom/sidecar.py::snapshot
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- verify: groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch
- detail: [sidecar snapshot](sidecar-snapshot.md#method-snapshot)
- refs: [sidecar snapshot data](../sidecar-snapshot-data.md), [sidecar run checkpoint data](../sidecar-run-checkpoint-data.md), [sidecar run metadata](../sidecar-run-metadata.md)
- input: no call arguments; uses [field-workspace-dir](#field-workspace-dir) and
  [field-runs-dir](#field-runs-dir).
- output: one object with `current_node`, `terminal`, and `gates` keys.
- does:
  - Reads the latest current graph-node id from the latest checkpoint.
  - Reads the latest terminal marker from the latest run metadata.
  - Calls [method-scan-gates](#method-scan-gates) for all currently awaiting gate
    entries.
  - Performs no network I/O, inotify subscription, stdout write, process exit, or
    filesystem mutation.

### concept: ReloadRequested

ReloadRequested is the sidecar-local reload control signal raised by the
[sidecar connected session](sidecar-connected-session.md) after it receives a
host `reload` [sidecar websocket frame](../sidecar-websocket-frame.md). The
[sidecar serving loop](sidecar-serving-loop.md) catches it, closes the current
socket best-effort, and converts it into the reserved reload exit code consumed
by the container entrypoint.

- sig: `class ReloadRequested(Exception)`
- abstract: false
- code: groom/groom/sidecar.py::ReloadRequested
- verify: groom/tests/test_sidecar_session.py::test_run_session_advertises_hello_then_reload_raises,
  groom/tests/test_sidecar_session.py::test_serve_returns_reload_code_when_session_requests_reload
- refs: [sidecar connected session](sidecar-connected-session.md), [sidecar serving loop](sidecar-serving-loop.md), [sidecar websocket frame](../sidecar-websocket-frame.md)
- role: internal exception class used only as an in-process control signal; it is
  not serialized on the websocket and is not exposed through the CLI or HTTP API.
- trigger: raised only by a connected sidecar session after decoding an inbound
  websocket message whose `type` field is `reload`.
- base: standard-library `Exception`; no Groom-specific base concept is created
  for the external standard-library class.
- fields: none; instances carry no structured attributes, status object, retry
  hint, correlation id, container id, or websocket payload.
- methods: none beyond standard exception behavior; it defines no custom
  constructor, formatter, serializer, or recovery hook.
- construction: ordinary exception construction only; current callers raise the
  class without arguments, so no message is part of the sidecar reload contract.
- catch boundary: handled by the sidecar serving loop; the connected-session
  cleanup block still runs before the exception reaches that boundary.
- does:
  - Marks the exact moment a connected sidecar session has accepted a host
    `reload` command.
  - Unwinds the connected session through normal exception propagation after the
    session cleanup block removes the inotify reader, cancels the outbound sender,
    suppresses expected cancellation/socket-close cleanup errors, and closes the
    inotify handle.
  - Lets the serving loop distinguish intentional reload from ordinary websocket
    closure, so reload stops reconnecting while normal socket closure continues
    the reconnect loop.
  - Causes the serving loop to close the current websocket best-effort and return
    [field-reload-exit-code](#field-reload-exit-code) to the sidecar runner.
  - Does not encode success/failure data, mutate workspace files, send an
    acknowledgement frame, perform residual HTTP push, decide workflow status, or
    change the host registry directly.

### method-run

- sig: `run() -> None`
- abstract: false
- raises: `SystemExit(exit_code)` when the serving loop returns a truthy integer;
  exceptions raised by the serving loop before it returns propagate unchanged.
- code: groom/groom/sidecar.py::run
- verify: groom/tests/test_sidecar_session.py::test_run_maps_reload_code_to_systemexit
- detail: [sidecar live session runner](sidecar-live-session-runner.md)
- refs: [sidecar serving loop](sidecar-serving-loop.md), [`groom-sidecar`](../groom-sidecar.md#groom-sidecar-root)
- input: no call arguments; runtime configuration is inherited from module fields.
- output: returns `None` only when the serving loop returns zero.
- does:
  - Starts one blocking run of the async sidecar serving loop.
  - Converts any non-zero returned serving-loop code into a process exit with the
    same numeric code.
  - Performs no parsing, snapshot read, residual HTTP push, websocket connection,
    or inotify setup before delegating to the serving loop.

## Folded Private Helper Contract

- identity producer: `groom/groom/sidecar.py::_identity` is folded into [sidecar identity data](../sidecar-identity-data.md); it derives `container_id`, `name`, `repo_name`, and `repo_branch` from hostname and repository environment variables.
- residual push core: `groom/groom/sidecar.py::_push` is folded into [sidecar residual HTTP push helper](sidecar-residual-http-push-helper.md); it merges identity and event fields, serializes JSON, and performs one best-effort HTTP `POST`.
- run-state readers: `groom/groom/sidecar.py::_latest_run_dir`, `groom/groom/sidecar.py::_current_node`, and `groom/groom/sidecar.py::_terminal` are folded into [sidecar snapshot](sidecar-snapshot.md); they select the latest run directory, checkpoint current node, and terminal marker.
- watch installer: `groom/groom/sidecar.py::_add_watches` is folded into [sidecar recursive watch installer](sidecar-recursive-watch-installer.md); it installs recursive inotify watches while pruning skipped directories.
- event classifiers: `groom/groom/sidecar.py::_classify_event` is folded into [sidecar websocket frame](../sidecar-websocket-frame.md#method-_classify_event); `groom/groom/sidecar.py::_handle_event` is the residual HTTP adapter for the same classification result and emits progress or blocked push wrappers.
- path guard and repository readers: `groom/groom/sidecar.py::_safe_relpath`, `groom/groom/sidecar.py::_repo_base`, `groom/groom/sidecar.py::_find_repo_dirs`, `groom/groom/sidecar.py::_list_tree`, and `groom/groom/sidecar.py::_git_diff` are folded into [sidecar-local relative path guard](sidecar-local-relative-path-guard.md), [workspace file list data](../workspace-file-list-data.md), and [workspace diff data](../workspace-diff-data.md).
- RPC handlers: `groom/groom/sidecar.py::_rpc_get_tree`, `groom/groom/sidecar.py::_rpc_get_file`, and `groom/groom/sidecar.py::_rpc_get_diff` are folded into [workspace file list data](../workspace-file-list-data.md), [workspace file content data](../workspace-file-content-data.md), and [workspace diff data](../workspace-diff-data.md); `groom/groom/sidecar.py::_handle_rpc` is folded into [sidecar websocket frame](../sidecar-websocket-frame.md#method-_handle_rpc).
- session helpers: `groom/groom/sidecar.py::_hello_frame`, `groom/groom/sidecar.py::_sender_loop`, `groom/groom/sidecar.py::_run_session`, and `groom/groom/sidecar.py::_serve` are folded into [sidecar websocket frame](../sidecar-websocket-frame.md#method-_hello_frame), [sidecar outbound sender](sidecar-outbound-sender.md), [sidecar connected session](sidecar-connected-session.md), and [sidecar serving loop](sidecar-serving-loop.md).

## Module Flow

1. Query mode reaches [method-snapshot](#method-snapshot) through the
   [`groom-sidecar-root`](../groom-sidecar.md#groom-sidecar-root) invocation and
   returns its object as JSON without starting a live session.
2. Exit-notice mode reaches [method-push-exited](#method-push-exited) through the
   same CLI invocation and sends one residual HTTP notice after workhorse exits.
3. Default mode reaches [method-run](#method-run), starts the serving loop, and
   dials [websocket-sidecar](../http/groom.md#websocket-sidecar).
4. Each connected session emits a `hello` frame built from sidecar identity and a
   fresh snapshot, then observes workspace and run filesystem events.
5. Runs events emit `progress` frames; awaiting gate file events emit `blocked`
   frames; directory events extend the watch set without emitting protocol frames.
6. Host `rpc` frames are answered from local workspace data as correlated
   `rpc_result` frames, with handler errors represented as failed results.
7. Host `reload` frames raise the module's reload control exception so the serving
   loop returns the reserved reload exit code and the runner surfaces it to the
   container entrypoint.

## Non-Responsibilities

- Does not define the `groom-sidecar` argument parser; that belongs to the [Groom
  CLI entrypoints module](groom-cli-entrypoints-module.md#method-sidecar-main).
- Does not apply sidecar `hello`, `progress`, `blocked`, or `rpc_result` frames to
  host workflow state; those effects belong to the host [Groom app module](groom-app-module.md)
  and [sidecar connection](sidecar-connection.md) concepts.
- Does not provide Docker fallback reads; host fallback behavior belongs to the
  [Groom Docker I/O module](groom-docker-io-module.md) and workspace-volume reader
  concepts.
- Does not write gate answers or workspace files; operator answers are handled by
  the [gate answering layer](gate-answering-layer.md) and workspace-volume writer.
