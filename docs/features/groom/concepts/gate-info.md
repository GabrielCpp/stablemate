---
type: concept
slug: gate-info
title: Gate info
---
# Gate info

Gate info is the in-memory record for one live operator gate on a [workflow container](workflow-container.md) in the process-local [workflow registry](workflow-registry.md). The [receive blocked push](../http/groom.md#receive-blocked-push) invocation creates or replaces this record from a [blocked push payload](../blocked-push-payload.md), the [websocket-sidecar](../http/groom.md#websocket-sidecar) invocation rebuilds it from `hello` [sidecar websocket frame](../sidecar-websocket-frame.md) [sidecar snapshot data](../sidecar-snapshot-data.md), Docker discovery can rebuild it from awaiting gate context files or a sidecar query snapshot, and dashboard fragments render its file path and question into inbox rows and worker-detail answer forms. The [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) targets a gate by workflow id and file path, the [gate-answering layer](gate-answering-layer.md) removes the record only after the corresponding gate file is successfully answered, and terminal or vanished workflow states remove gate info by clearing or dropping the containing workflow record.

- code: groom/groom/models.py::GateInfo
- verify: groom/tests/test_discovery.py::test_find_gates_only_keeps_files_still_awaiting
- verify: groom/tests/test_discovery.py::test_scan_uses_sidecar_query_for_running_container
- verify: groom/tests/test_render.py::test_gate_question_rendered_as_escaped_data_md_text_node
- verify: groom/tests/test_render.py::test_worker_detail_has_ws_send_answer_form
- verify: groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code
- verify: groom/tests/test_app.py::test_handle_answer_flips_state_and_broadcasts_answered_script
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate
- verify: groom/tests/test_app.py::test_apply_hello_finished_when_terminal
- verify: groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively
- verify: groom/tests/test_state.py::test_prune_also_forgets_gate_locks_of_removed

## Contract

- shape: mutable dataclass record with generated initialization, representation, and value equality over `workflow_id`, `file_path`, `question`, and `status`; it defines no ordering, hashing, validation, post-init hook, custom methods, or class-level registry.
- construction: callers must provide `workflow_id` and `file_path`; callers may omit `question` to store an empty prompt and may omit `status` to store `AWAITING_OPERATOR`.
- identity: a gate is scoped by the pair `(workflow_id, file_path)`; the containing workflow stores gates in a dictionary keyed by the same `file_path`, so a single workflow can hold multiple simultaneous open gates.
- creation from blocked push: residual `/push/blocked` handling string-normalizes and requires `container_id` and `file_path`, truncates the container id to 12 characters, stores `workflow_id` and `file_path` from those normalized values, stores `question` from `str(data.get("question", ""))`, and leaves `status` at the dataclass default.
- creation from sidecar hello: a useful sidecar `hello` clears any existing gates for that workflow before applying the advertised snapshot; a terminal snapshot leaves the gate map empty and marks the workflow finished, otherwise each snapshot gate with a non-empty string-normalized `file_path` becomes one record with `workflow_id` equal to the connected container id, `file_path` from the snapshot entry, `question` from `str(gate.get("question", ""))`, and the default status.
- creation from Docker discovery: volume discovery creates records only for files whose current status is `AWAITING_OPERATOR`; the discovered record is keyed by file path, later filled with the resolved workflow container id when the record came from a workspace-volume scan.
- creation from sidecar query discovery: running-container discovery that receives a sidecar query snapshot creates one record per snapshot gate with a non-empty `file_path`, uses the discovered workflow container id as `workflow_id`, trusts the snapshot `question` value as already text without additional string conversion, and explicitly stores `AWAITING_OPERATOR` status; a terminal snapshot wins over any advertised or previously known gates.
- creation from sidecar blocked delta: sidecar `blocked` frames with a non-empty string-normalized `file_path` insert or replace one record for the connected container id, set workflow state to blocked, and keep the default status.
- replacement: later blocked pushes, sidecar blocked deltas, sidecar hello snapshots, or discovery results for the same file path replace the previous record at that key; there is no merge of question/status fields across replacements.
- removal: successful answer handling removes only the matching `(workflow_id, file_path)` record under that pair's answer lock; failed or stale answer attempts leave the record unchanged, workflow exit clears every gate record for that workflow, and workflow pruning removes gate info by dropping the vanished workflow container from the registry.
- visibility: a workflow with at least one gate appears in the operator inbox; inbox rows display the first gate after sorting by file path, and worker detail renders every open gate sorted by file path.
- rendering safety: file paths and questions are escaped before insertion into HTML; worker detail places the question in a `data-md` text node for client-side sanitized markdown rendering, never as raw HTML.
- state: the only first-party open status value is `AWAITING_OPERATOR`; the model records no answered timestamp, answer text, retry count, persistence handle, source transport, or last-seen timestamp.
- persistence: no database or host-side file persists this record; process restart rebuilds open gates from discovery, sidecar query snapshots, sidecar `hello` snapshots, sidecar blocked deltas, or later residual pushes.
- mutation boundary: the dataclass itself performs no validation, normalization, locking, I/O, answer application, rendering, broadcasting, sidecar registration, or workflow-state transition.

## Fields

### field-workflow-id

- type: `str`
- default: none
- required: true
- meaning: normalized workflow container id that owns this gate and scopes answer commands.
- source: residual push handlers use `str(container_id)[:12]`; sidecar websocket handlers use the connected container id established by hello; discovery assigns the resolved container id after reconstructing gates from a workspace volume.
- constraints: not validated by the dataclass; a useful record has a non-empty id because consumers use it to find the workflow container and workspace volume.

### field-file-path

- type: `str`
- default: none
- required: true
- meaning: gate context-file path; this is both the map key in `WorkflowContainer.gates` and the path written into hidden answer-form data.
- source: residual blocked pushes and sidecar blocked frames use `str(data.get("file_path", ""))`; sidecar hello and discovery use the workspace-relative path reported by the snapshot or awaiting-file scan.
- constraints: empty values are rejected or skipped by first-party creators before creating the record; non-empty values are not canonicalized by the dataclass.

### field-question

- type: `str`
- default: `""`
- required: false
- meaning: operator-facing prompt text rendered as escaped text for client-side markdown sanitization and used as the source for notification previews.
- source: blocked pushes and sidecar blocked frames use `str(data.get("question", ""))`; sidecar hello uses `str(gate.get("question", ""))`; workspace-volume discovery extracts text from an awaiting gate context file; sidecar query discovery copies the snapshot gate's `question` value or `""` when absent and expects that sidecar-produced value to already be text.
- constraints: may be empty, multiline, or markdown-like text; renderers assume text for line splitting and HTML escaping, so non-text values from non-first-party sidecar query snapshots are outside the supported contract and can fail rendering rather than being coerced here.

### field-status

- type: `str`
- default: `"AWAITING_OPERATOR"`
- required: false
- meaning: gate status label retained from the workhorse gate file; open gates created by blocked pushes keep this default until removed rather than mutating to an answered state.
- source: dataclass default for residual blocked pushes, sidecar `hello`, and sidecar blocked-delta paths; Docker volume discovery and sidecar query discovery explicitly set the same awaiting value after confirming or accepting an awaiting gate source.
- constraints: first-party code does not mutate this field after creation and does not model answered or consumed states in memory; non-awaiting volume gate files are filtered before records are created, while sidecar-reported open gates are treated as awaiting by construction.
