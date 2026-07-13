---
type: concept
slug: workflow-state
title: Workflow state
---
# Workflow state

Workflow state is the lifecycle enum stored on each [workflow container](workflow-container.md), used by the [operator inbox](../operator-inbox.md) to order actionable workers, counted and displayed by the [groom dashboard](../gui/screens/groom-dashboard.md), projected by the [workflow state dot renderer](workflow-state-dot-renderer.md), and mutated by the [groom server](../http/groom.md) from Docker discovery, residual push endpoints, sidecar websocket snapshots/deltas, and successful gate-answer handling. The enum is process-local display and routing state: it is rebuilt from [sidecar snapshot data](../sidecar-snapshot-data.md), Docker volume reads of [sidecar run metadata](../sidecar-run-metadata.md), [progress push payload](../progress-push-payload.md), [blocked push payload](../blocked-push-payload.md), and [exited push payload](../exited-push-payload.md) rather than persisted as its own file or database record.

- code: groom/groom/models.py::WorkflowState
- verify: groom/tests/test_discovery.py::test_container_from_inspect_reads_env_name_and_volumes
- verify: groom/tests/test_discovery.py::test_workflow_type_from_workflow_mount_basename
- verify: groom/tests/test_discovery.py::test_workflow_type_falls_back_to_compose_service_label
- verify: groom/tests/test_discovery.py::test_container_from_inspect_marks_stopped_container_idle
- verify: groom/tests/test_discovery.py::test_container_from_inspect_falls_back_to_id_when_unnamed
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_discovery.py::test_scan_query_terminal_wins_over_gates
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- verify: groom/tests/test_sidecar_session.py::test_classify_event_runs_write_is_progress
- verify: groom/tests/test_sidecar_session.py::test_classify_event_awaiting_gate_is_blocked
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate
- verify: groom/tests/test_app.py::test_apply_hello_running_when_no_gates
- verify: groom/tests/test_app.py::test_apply_hello_finished_when_terminal
- verify: groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively
- verify: groom/tests/test_render.py::test_statusbar_counts_states
- verify: groom/tests/test_render.py::test_inbox_orders_gated_workers_by_state_then_name
- verify: groom/tests/test_render.py::test_exit_code_hint_only_on_finished_with_code

## Contract

- type: `str` enum with exactly four canonical lowercase values: `running`, `blocked`, `idle`, and `finished`.
- identity: each enum member's value is the exact lower-case string emitted into HTML `data-state`, CSS dot classes, status text, and command-palette hints.
- member set: the groom-owned lifecycle vocabulary is exactly `RUNNING`, `BLOCKED`, `IDLE`, and `FINISHED`; there are no aliases, deprecated values, intermediate states, or first-party methods on the enum.
- storage: stored only as `WorkflowContainer.state` in the process-local [workflow registry](workflow-registry.md); no first-party path persists workflow state independently of the workflow container snapshot.
- default owner: new dataclass instances and registry upserts for previously unseen workflows default to `idle` unless the creating path supplies a more specific state.
- source precedence: terminal evidence wins over gates; gate evidence wins over running/idle; progress evidence sets running; an exited push sets finished and clears gates.
- mutation: server, registry, and discovery layers assign enum members directly; no parser accepts arbitrary lifecycle strings as supported workflow states, and registry upserts ignore `None` state values rather than clearing the current state.
- sorting: dashboard state order is `blocked`, then `running`, then `idle`, then `finished` for inbox rows and repository menu options.
- status order: status-bar counts are emitted in the order `blocked`, `running`, `idle`, then `finished`.
- rendering: rows, repository picker options, status text, state dots, command-palette hints, detail headers, no-open-gate messages, and exit-code hints consume the enum value as lowercase text.
- search: dashboard inbox search does not match the state string itself; it filters open-gate workflows by workflow name, repository name, repository branch, workflow type, current node, and gate file path.
- gate invariant: a workflow with open gates should normally be `blocked`; a successful last-gate answer changes only a still-existing `blocked` workflow with no remaining gates to `running`.
- terminal invariant: a `finished` workflow cannot act on an answer; exited handling clears open gates and terminal discovery/snapshot paths avoid applying gates after a terminal marker.
- connection invariant: sidecar websocket connection presence is not itself a workflow state; sidecar disconnect unregisters the live data-plane connection and fails pending RPCs, but does not change the stored workflow state or gate map.
- unknowns: missing or unavailable sidecar, Docker, run-artifact, or gate evidence preserves the current/default state for that path instead of inventing a new enum value.

## Transitions

### transition-registry-default-and-assignment

- from: workflow registry creation or partial update
- to: `idle` for a newly-created partial workflow when no explicit state is supplied; otherwise the supplied non-null enum member replaces the previous state.
- code: groom/groom/state.py::upsert_workflow
- meaning: lets residual pushes, sidecar frames, answer handling, and volume hydration build one workflow record incrementally without erasing state when an update omits lifecycle information.

### transition-discovery-initial

- from: [Docker inspect container object](../docker-inspect-container-object.md)
- to: a baseline [workflow container](workflow-container.md) whose state is `running` when `State.Running` is truthy and `idle` otherwise.
- code: groom/groom/discovery.py::container_from_inspect
- meaning: creates the baseline workflow record before sidecar query, run-volume, or gate-volume evidence refines it; this conversion also supplies the push-first resolver with volume and workflow-type metadata.
- reads: `Id`, `Name`, `State.Running`, `Config.Env`, `Config.Labels`, and `Mounts` from the inspect object; other Docker fields are ignored.
- indexes: the `Mounts` list by each row's `Destination` before reading `/workflow`, `/runs`, and `/workspace`, so mount order does not affect workflow type or volume extraction.
- parses: `Config.Env` through the [environment-map extractor](workflow-discovery-scan.md#method-extract-environment-map), accepting only `KEY=VALUE` strings, splitting at the first `=`, and retaining the later value when the same key appears more than once.
- maps: `Id` to the first twelve characters of `container_id`; `Name` to the display name after removing one leading slash, falling back to `container_id`; `REPO_NAME` and `REPO_BRANCH` environment entries to repository identity; missing environment keys to empty repository identity strings; `/workspace` and `/runs` mount names to volume fields.
- derives: `workflow_type` through the [workflow-type derivation method](workflow-discovery-scan.md#method-derive-workflow-type), using the basename of the `/workflow` mount source first and falling back to the `com.docker.compose.service` label when the basename is empty or the generic value `workflow`.
- preserves: unrelated environment variables, including secrets, are not copied into the workflow container record.
- default: missing inspect subtrees, missing mounts, missing labels, or environment entries without `=` become empty strings or false running state rather than errors in this conversion layer.

### transition-sidecar-query-or-discovery-snapshot

- from: sidecar query snapshot during discovery
- to: `finished` when the snapshot has a truthy terminal marker; `blocked` when the snapshot has one or more usable gate file paths; otherwise the baseline state remains in effect.
- code: groom/groom/discovery.py::_apply_snapshot
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_discovery.py::test_scan_query_terminal_wins_over_gates
- meaning: lets a running container report its own current node, terminal marker, and gates without host-side volume reconstruction; terminal snapshots return before gates are applied.

### transition-volume-reconstruction

- from: run-volume reads of [sidecar run metadata](../sidecar-run-metadata.md) and workspace-volume gate reads during discovery fallback
- to: `finished` when latest run metadata has a terminal marker; `blocked` when awaiting gate files are found and the workflow is not already finished.
- code: groom/groom/discovery.py::_resolve_via_volumes
- verify: groom/tests/test_discovery.py::test_scan_marks_blocked_workflow_and_finished_run
- verify: groom/tests/test_discovery.py::test_scan_stopped_container_skips_query_and_reads_volumes
- meaning: reconstructs state for stopped containers and running containers whose sidecar query is unavailable; gate scanning is skipped after terminal run metadata marks the workflow finished.

### transition-progress-push

- from: [progress push payload](../progress-push-payload.md)
- to: `running`
- code: groom/groom/app.py::push_progress
- meaning: marks the workflow active and optionally refreshes the current-node and identity fields before broadcasting the dashboard shell.

### transition-blocked-push

- from: [blocked push payload](../blocked-push-payload.md)
- to: `blocked`
- code: groom/groom/app.py::push_blocked
- meaning: records or replaces one [gate info](gate-info.md) entry for the reported file path, marks the workflow blocked, broadcasts the dashboard shell, and appends the blocked-notification script fragment.

### transition-exited-push

- from: [exited push payload](../exited-push-payload.md)
- to: `finished`
- code: groom/groom/app.py::push_exited
- meaning: marks the workflow terminal, stores a numeric exit code when supplied, preserves the existing exit-code field when the payload omits it or supplies a non-numeric value, clears all open gates, and broadcasts the dashboard shell without removing the workflow from the registry.

### transition-successful-last-gate-answer

- from: [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md)
- to: `running`
- code: groom/groom/app.py::_handle_command
- meaning: after the [gate-answering layer](gate-answering-layer.md) succeeds, if the workflow still exists, has no remaining gates, and was `blocked`, the server marks it running before broadcasting the answered shell fragment.

### transition-sidecar-hello

- from: [sidecar websocket frame](../sidecar-websocket-frame.md) with type `hello` and [sidecar snapshot data](../sidecar-snapshot-data.md)
- to: `finished` for a terminal snapshot; `blocked` when the rebuilt gate map is non-empty; `running` when the connected sidecar reports no terminal marker and no gates.
- code: groom/groom/app.py::_apply_hello
- meaning: treats each connected sidecar hello as authoritative for current node and gates by clearing stale gates and rebuilding the visible lifecycle state from the snapshot; a non-terminal empty-gate reconnect turns a previously blocked workflow back to running.

### transition-sidecar-progress

- from: [sidecar websocket frame](../sidecar-websocket-frame.md) with type `progress`
- to: `running`
- code: groom/groom/app.py::_apply_socket_progress
- meaning: applies a live connected-container progress delta and broadcasts the dashboard shell.

### transition-sidecar-blocked

- from: [sidecar websocket frame](../sidecar-websocket-frame.md) with type `blocked`
- to: `blocked`
- code: groom/groom/app.py::_apply_socket_blocked
- meaning: requires a non-empty gate file path, records or replaces one gate, broadcasts the dashboard shell, and appends the blocked-notification script fragment.

### transition-sidecar-disconnect-no-state-change

- from: [sidecar websocket frame](../sidecar-websocket-frame.md) session cleanup after a useful `hello` registered a [sidecar connection](sidecar-connection.md)
- to: unchanged workflow state
- code: groom/groom/app.py::dashboard_sidecar
- verify: groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection
- meaning: unregisters the live sidecar connection and fails its pending RPCs, but leaves the workflow container's current lifecycle state, current node, exit code, and gate map unchanged until a later hello, progress, blocked, exited push, answer, or discovery pass supplies new lifecycle evidence.

## Fields

### field-running

- type: enum member
- default: not the enum default
- required: true
- value: `running`
- code: groom/groom/models.py::WorkflowState.RUNNING
- meaning: the workflow is active, connected without open gates, progressing through a node, or has just resumed after its last open gate was answered.
- sources: Docker discovery for running containers, progress push handling, sidecar progress frames, sidecar hello snapshots without terminal or gates, and successful last-gate answer handling.
- displays: contributes to running status-bar count, sorts after blocked and before idle, renders a `running` state dot/text, appears in repository-picker order, and is omitted from the operator inbox unless open gates still exist.

### field-blocked

- type: enum member
- default: not the enum default
- required: true
- value: `blocked`
- code: groom/groom/models.py::WorkflowState.BLOCKED
- meaning: the workflow has at least one open operator gate that can be shown in the operator inbox and answered from the dashboard.
- sources: blocked push handling, sidecar blocked frames, sidecar hello snapshots with gates, sidecar query snapshots with gates, and workspace-volume gate reconstruction.
- displays: contributes to blocked status-bar count, sorts before every other state, appears in the operator inbox when gates are open, adds blocked row styling and question preview when the selected gate has a question, and remains unchanged after a failed answer attempt.

### field-idle

- type: enum member
- default: `WorkflowState.IDLE`
- required: true
- value: `idle`
- code: groom/groom/models.py::WorkflowState.IDLE
- meaning: the workflow has a record but no active, blocked, or terminal evidence has been supplied yet.
- sources: dataclass default, registry upsert default for a newly seen workflow without supplied state, and Docker discovery for stopped containers before run-volume or gate-volume evidence refines the record.
- displays: contributes to idle status-bar count, sorts after running and before finished, renders an `idle` state dot/text, appears in repository-picker order, and is omitted from the operator inbox unless open gates still exist.

### field-finished

- type: enum member
- default: not the enum default
- required: true
- value: `finished`
- code: groom/groom/models.py::WorkflowState.FINISHED
- meaning: the workflow process has ended and cannot act on an answer.
- sources: exited push handling, sidecar hello snapshots with a terminal marker, sidecar query snapshots with a terminal marker, and run-volume reconstruction with a terminal marker.
- displays: contributes to finished status-bar count, sorts last, renders a `finished` state dot/text, appears after live workers in repository-picker order, may show an exit-code hint when `WorkflowContainer.exit_code` is known, and is omitted from the operator inbox unless a stale gate map is still present.
