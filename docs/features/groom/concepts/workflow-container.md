---
type: concept
slug: workflow-container
title: Workflow container
---
# Workflow container

Workflow container is the in-memory record for one workhorse-backed container that `groom` can show, query, and update. The [groom server](../http/groom.md) stores these records in its process-local [workflow registry](workflow-registry.md), creates and refreshes them from Docker discovery, [sidecar snapshot data](../sidecar-snapshot-data.md), [progress push payloads](../progress-push-payload.md), [blocked push payloads](../blocked-push-payload.md), and [exited push payloads](../exited-push-payload.md), exposes them through dashboard endpoints such as the [search fragment](../http/groom.md#get-search-fragment), [worker detail](../http/groom.md#get-worker-detail), and [repository menu](../http/groom.md#get-repository-menu), records open [gate info](gate-info.md) entries for blocked gates, and renders them into controls such as the [inbox worker row](../gui/screens/groom-dashboard.md#inbox-worker-row) and [repository menu option](../gui/screens/groom-dashboard.md#repository-menu-option). The [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) targets a workflow container by id so the answer path can find the workflow's workspace volume and open gate map.

- code: groom/groom/models.py::WorkflowContainer
- verify: groom/tests/test_discovery.py::test_container_from_inspect_reads_env_name_and_volumes
- verify: groom/tests/test_discovery.py::test_workflow_type_from_workflow_mount_basename
- verify: groom/tests/test_discovery.py::test_workflow_type_falls_back_to_compose_service_label
- verify: groom/tests/test_discovery.py::test_container_from_inspect_marks_stopped_container_idle
- verify: groom/tests/test_discovery.py::test_container_from_inspect_falls_back_to_id_when_unnamed
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_handle_answer_failure_does_not_flip_or_dispatch
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate
- verify: groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively
- verify: groom/tests/test_render.py::test_inbox_shows_only_workers_with_open_gates
- verify: groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form

## Contract

- identity: `container_id` is the stable key used by HTTP routes, websocket commands, sidecar registrations, dashboard data attributes, and the in-memory registry.
- creation: Docker discovery constructs a full record from `docker inspect`; registry upserts construct a partial record when a residual push or sidecar frame first references an unknown container id, using the supplied non-null name or `container_id[:12]` as the display name.
- lifecycle: records are created or updated by startup discovery, manual refresh, residual HTTP progress/blocked/exited pushes, sidecar websocket hello/progress/blocked frames, and successful answer handling; they remain in memory until pruned by discovery or lost on process exit.
- source precedence: manual/startup discovery replaces the registry entry with the discovered snapshot; sidecar hello preserves existing fields not carried by the sidecar, then rebuilds current node, terminal state, and gates authoritatively for a connected container; point updates ignore `None` values so omitted fields preserve the previous value.
- volume hydration: push and sidecar paths that do not carry Docker volume metadata call the volume resolver before mutating the workflow; existing non-empty workspace volume data is preserved.
- terminal precedence: a terminal sidecar snapshot or exited push marks the workflow finished and prevents or clears open gates because an exited workflow cannot act on an answer.
- gate model: `gates` is keyed by gate file path; a blocked push or sidecar blocked frame inserts or replaces one gate, a sidecar hello snapshot clears and rebuilds all gates, and a successful answer removes the answered gate through the gate-answering layer.
- answer transition: the dashboard answer command reads the workflow by submitted id only to obtain `workspace_volume` and decide the post-answer state transition; when the answer succeeds, the workflow still exists, no gates remain, and its state is blocked, the workflow state changes immediately to running before the refreshed dashboard shell is broadcast and before the success-only `groom:answered` browser event is appended.
- visibility: records with open gates appear in the [operator inbox](../operator-inbox.md); all records contribute to status counts; records with a known workspace volume are eligible for file, diff, and repository-picker data-plane operations.
- search projection: the [serve search fragment](../http/groom.md#serve-search-fragment) invocation filters only workflow containers that currently have one or more open gates, and its case-insensitive query haystack is the workflow name, repository name, repository branch, workflow type, current node, and each open gate file path. Container id, gate question text, exit code, volume names, run id, and update timestamp are not search fields.
- rendering: renderer functions consume the record as display data, escape text fields before HTML insertion, sort gates by file path for the worker detail pane, and sort/filter workflow lists outside the dataclass.
- mutability: records are mutable while the groom process is alive; fields may be filled incrementally as sidecar state, residual pushes, answer handling, and Docker metadata arrive through different paths.
- mutation rules: registry upsert mutates only attributes that exist on the dataclass and whose incoming value is not `None`; unknown field names and `None` values are ignored rather than recorded.
- validation boundary: the dataclass itself performs no validation, normalization, locking, Docker I/O, websocket I/O, gate-file writes, HTML rendering, broadcasting, or persistence; callers own those behaviors.
- persistence: no database or file persists this record; process restart rebuilds it from discovery and sidecar reconnects.
- construction: callers must provide `container_id` and `name`; every other field may be omitted and then uses the dataclass default documented below.
- methods: no groom-owned methods are defined on the class; construction, representation, and equality behavior come from standard dataclass machinery and are not separate groom crawl targets.
- reference types: `state` is a [workflow state](workflow-state.md) value and `gates` stores [gate info](gate-info.md) values; those sibling concepts own their allowed values and fields.

## Fields

### field-container-id

- type: `str`
- default: none
- required: true
- meaning: container identifier used as the map key, route path value, sidecar connection id, and `data-container` value in repository menu options.
- source: discovery uses the first 12 characters of Docker inspect `Id`; residual HTTP push handlers and sidecar websocket hello normalize incoming ids with `str(value)[:12]`; dashboard answer frames use the submitted workflow id as-is to look up the record.
- constraints: not validated by the dataclass; a useful value is non-empty and stable for the lifetime of the Docker container.

### field-name

- type: `str`
- default: none
- required: true
- meaning: human-facing workflow/container label shown in rows and repository picker labels.
- source: discovery uses Docker inspect `Name` without its leading slash, falling back to `container_id`; registry upsert for a new partial record uses the supplied non-null `name`, otherwise `container_id[:12]`; push and sidecar identity fields replace the existing name only when non-null.
- constraints: renderers escape the value before HTML insertion; the dataclass does not require it to be unique.

### field-repo-name

- type: `str`
- default: `""`
- required: false
- meaning: repository name shown in dashboard identity text when known.
- source: discovery reads `REPO_NAME` from container environment; residual push and sidecar identity fields replace it only when non-null.
- constraints: empty means unknown; renderers display an em dash placeholder when neither repository name nor branch is known.

### field-repo-branch

- type: `str`
- default: `""`
- required: false
- meaning: repository branch shown alongside `repo_name` when known.
- source: discovery reads `REPO_BRANCH` from container environment; residual push and sidecar identity fields replace it only when non-null.
- constraints: empty suppresses the `@branch` suffix in the repository label.

### field-workflow-type

- type: `str`
- default: `""`
- required: false
- meaning: workflow kind badge text, for example author or coder, when supplied by discovery or sidecar state.
- source: discovery derives it through the [workflow-type derivation method](workflow-discovery-scan.md#method-derive-workflow-type), reading the `/workflow` mount source basename first and falling back to the compose service label when the basename is empty or generic; push-first volume hydration can fill it for records first seen through sidecar or residual push events.
- constraints: empty suppresses the type badge; non-empty values are rendered as escaped text and may be any workflow kind string.

### field-state

- type: [workflow state](workflow-state.md)
- default: `WorkflowState.IDLE`
- required: false
- meaning: visible lifecycle state; allowed values are `running`, `blocked`, `idle`, and `finished`.
- source: dataclass default is idle; discovery uses running for running containers and idle for stopped containers before sidecar/volume state resolution; progress events set running; blocked events and snapshots with gates set blocked; terminal snapshots and exited pushes set finished.
- constraints: successful answer handling may set blocked to running after the last gate clears; exited handling clears all gates while setting finished.

### field-current-node

- type: `str`
- default: `""`
- required: false
- meaning: current workhorse node label shown in dashboard metadata when known.
- source: sidecar snapshots, sidecar progress frames, residual progress pushes, and runs-volume discovery can supply or update this value.
- constraints: empty means unknown; point updates preserve the existing value when the incoming value is `None`, while sidecar hello and discovery may leave it unchanged when the snapshot has no current node.

### field-run-id

- type: `str`
- default: `""`
- required: false
- meaning: workhorse run identifier when discovery or sidecar data can provide it.
- source: reserved by the record contract; current first-party discovery and push paths do not populate it.
- constraints: empty means unknown; renderers and data-plane handlers do not require it.

### field-workspace-volume

- type: `str`
- default: `""`
- required: false
- meaning: Docker volume containing the workflow workspace; non-empty enables repository listing, file tree reads, file content reads, diff reads, and gate file writes.
- source: Docker discovery reads the named `/workspace` mount; push-first volume hydration fills it from Docker inspect for records first seen through push or sidecar paths.
- constraints: empty disables volume-read fallback, repository listing, file/diff reads, and successful gate answering through the dashboard answer path.

### field-runs-volume

- type: `str`
- default: `""`
- required: false
- meaning: Docker volume containing workhorse run artifacts when discovered.
- source: Docker discovery reads the named `/runs` mount; push-first volume hydration fills it from Docker inspect for records first seen through push or sidecar paths.
- constraints: empty disables host-side current-node and terminal reconstruction from run artifacts.

### field-updated-at

- type: `str`
- default: `""`
- required: false
- meaning: timestamp text reserved for last-update display or ordering when supplied by producers.
- source: reserved by the record contract; current first-party discovery, push, sidecar, answer, and rendering paths do not populate it.
- constraints: empty means no timestamp is available; no renderer currently orders or filters by this field.

### field-exit-code

- type: `int | None`
- default: `None`
- required: false
- meaning: process exit code for a finished workflow when known; absent for live workers and finished workers without an exit report.
- source: exited push handling stores integers and numeric strings with an optional leading minus sign; non-numeric or absent values preserve the existing value.
- constraints: `None` suppresses exit-code hint rendering; non-zero values render as error exits and zero renders as an ok exit; non-numeric exited-push values are converted to `None` by the caller and then ignored by registry upsert, so any previous exit code is preserved.

### field-gates

- type: `dict[str, GateInfo]`
- default: new empty dictionary per workflow container
- required: false
- meaning: open operator [gate info](gate-info.md) records keyed by gate file path; non-empty gates make the workflow an inbox message and drive answer forms.
- source: blocked pushes and sidecar blocked frames insert one gate by file path; sidecar hello snapshots clear and rebuild the map; discovery reconstructs gates from sidecar query or workspace-volume scans; exited pushes clear the whole map; successful answers remove the answered gate through the gate-answering layer.
- constraints: keys are file-path strings; a workflow can have more than one gate; renderers sort values by file path before choosing the inbox preview or rendering worker-detail blocks.
