---
type: concept
slug: workflow-registry
title: Workflow registry
---
# Workflow registry

The workflow registry is groom's process-local map of live [workflow containers](workflow-container.md), keyed by container id and read by the [groom server](../http/groom.md). The [serve search fragment](../http/groom.md#serve-search-fragment) invocation reads it through the [all workflows snapshot](#method-all-workflows-snapshot) method before rendering the [operator inbox](../operator-inbox.md); the [receive progress push](../http/groom.md#receive-progress-push), [receive blocked push](../http/groom.md#receive-blocked-push), and [receive exited push](../http/groom.md#receive-exited-push) invocations update entries through the [upsert workflow](#method-upsert-workflow) method; and the [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) invocation updates it through the [reconcile workflow fleet](#method-reconcile-workflow-fleet) method, which consumes the [workflow discovery scan](workflow-discovery-scan.md), replaces discovered entries, and delegates stale-container deletion to [prune workflows](#method-prune-workflows). The [exited push payload](../exited-push-payload.md) terminal path preserves registry membership while marking one workflow finished, storing an accepted exit code, and clearing all open gates on that workflow; removal remains a later discovery-prune concern. The [per-gate answer lock](per-gate-answer-lock.md) registry is cleaned when vanished workflows are pruned, while the [workflow gate clearer](workflow-gate-clearer.md) removes one answered gate from a workflow already stored here. Other server paths use the same registry to populate the [worker tree](../worker-tree.md), repository picker, file/diff reads, websocket shell updates, sidecar snapshot application, and gate-answer routing.

- code: groom/groom/state.py::WORKFLOWS
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate
- verify: groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers
- verify: groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable
- verify: groom/tests/test_state.py::test_prune_drops_absent_keeps_present
- verify: groom/tests/test_state.py::test_prune_empty_present_removes_everything
- verify: groom/tests/test_state.py::test_prune_also_forgets_gate_locks_of_removed
- verify: groom/tests/test_state.py::test_prune_is_noop_when_all_present

## Contract

- scope: one in-memory registry per groom process; it is shared by HTTP handlers, websocket handlers, discovery, residual push endpoints, and sidecar session handling inside that process.
- key: workflow container id string, normally the twelve-character normalized container id used by dashboard routes and sidecar messages.
- value: mutable [workflow container](workflow-container.md) record for the keyed worker.
- lifetime: starts empty on process start, is repopulated by discovery or sidecar/backstop pushes, is pruned when discovery confirms containers have vanished, and is lost on process exit.
- ordering: readers must not treat registry order as semantic fleet order; renderers and handlers that need stable presentation order sort or filter the snapshot they receive.
- concurrency: no cross-process coordination, database, or external broker participates; all registry reads and writes are local to the running groom process.
- mutation channels: discovery reconciliation may replace whole workflow records; push and sidecar paths use partial upserts; gate answering mutates a selected workflow's gate map after file-write success; exited pushes clear all gates on the selected workflow; pruning deletes whole entries.
- partial update rule: upserts preserve existing values when a field is omitted, supplied as `None`, or not a workflow-container attribute, allowing sparse push and sidecar events to converge without erasing data from earlier discovery.
- direct replacement rule: reconciliation assigns each discovered workflow container directly into the map, so the discovered snapshot becomes authoritative for that container id before any stale-container pruning decision.
- lookup rule: read paths that fetch a registry entry by container id treat a missing workflow as absent data and do not create records; only the upsert and discovery-replacement paths add entries.
- direct lookup consumers: worker detail, file reads, diff reads, gate-answer routing, and workspace-volume checks read `WORKFLOWS.get(container_id)` and convert a missing entry into that caller's empty-state, empty-body, absent-workspace, or failed-answer behavior rather than creating placeholder workflows.
- gate-map rule: generic upsert preserves gate maps unless a caller explicitly supplies a non-null `gates` field; first-party progress paths do not clear gates, blocked paths add or replace one gate, sidecar hello replaces the entire gate map from a snapshot, successful answer handling removes one gate through the gate clearer, and exited-push handling clears every gate after the terminal upsert returns.
- terminal update rule: a valid exited push keeps the workflow entry in the registry, sets [workflow state](workflow-state.md) to `finished`, applies only accepted non-null identity and exit-code fields, clears the returned workflow's gate map, and leaves deletion to a later reconciliation prune.
- outage safety: a discovery present-id lookup of `None` means the registry cannot know which containers still exist, so pruning is skipped and existing entries remain visible.

## Fields

### field-workflows-map

- type: `dict[str, WorkflowContainer]`
- default: `{}` at process start
- required: true
- meaning: process-local registry storage shared by groom HTTP handlers, websocket handlers, discovery reconciliation, push handlers, and sidecar appliers.
- constraints: not persisted, not cloned on reads, not synchronized across processes, and not safe to treat as sorted presentation data.

### field-container-id-key

- type: `str`
- default: none
- required: true
- meaning: map key and route/message identifier for one tracked workflow container.
- constraints: the registry treats keys as opaque strings; normalizing to the twelve-character Docker id prefix is done by callers before lookup or mutation.

### field-workflow-container-value

- type: [workflow container](workflow-container.md)
- default: none
- required: true
- meaning: mutable record containing the worker identity, state, current node, Docker volume metadata, exit code, and open gate map shown by the dashboard.
- constraints: the registry stores object references; snapshots of registry values do not clone workflow containers or freeze later field mutation.

## Methods

### method-all-workflows-snapshot

- sig: `_all_workflows() -> list[WorkflowContainer]`
- abstract: false
- raises: none intentionally raised for an empty or populated registry.
- code: groom/groom/app.py::_all_workflows

Returns a new list containing the current registry values. The snapshot freezes only membership of the returned sequence at the moment of the call; the list items remain the same mutable [workflow container](workflow-container.md) objects held by the registry.

#### Effects

- Reads: every current value in the process-local `WORKFLOWS` mapping.
- Emits: a `list[WorkflowContainer]` whose length is the number of tracked workflow entries at read time, preserving the registry's current value iteration order without declaring that order meaningful.
- Preserves: registry keys, stored workflow records, gate maps, discovery state, sidecar state, and dashboard websocket clients.
- Does not: sort, filter, clone workflow objects, mutate registry entries, inspect Docker, contact sidecars, render HTML, broadcast websocket fragments, or write gate files.

### method-upsert-workflow

- sig: `upsert_workflow(container_id: str, **fields: object) -> WorkflowContainer`
- abstract: false
- raises: no domain-specific errors; ordinary Python call-binding, workflow-container construction, or attribute-assignment errors propagate to the caller.
- code: groom/groom/state.py::upsert_workflow
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate
- verify: groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively

Creates or updates one workflow registry entry and returns the exact mutable [workflow container](workflow-container.md) stored under the supplied container id. The method is shared by [receive progress push](../http/groom.md#receive-progress-push), [receive blocked push](../http/groom.md#receive-blocked-push), [receive exited push](../http/groom.md#receive-exited-push), [sidecar hello applier](sidecar-hello-applier.md), [sidecar progress applier](sidecar-progress-applier.md), [sidecar blocked applier](sidecar-blocked-applier.md), and push-first volume metadata resolution so sparse updates from different sources converge without erasing fields absent from the current event.

#### Parameters

- `container_id`: required string registry key. The method uses it exactly as supplied; HTTP and websocket callers normalize or truncate ids before calling.
- `fields`: optional keyword updates for [workflow container](workflow-container.md) attributes other than the required positional `container_id`. Recognized update names are `name`, `repo_name`, `repo_branch`, `workflow_type`, `state`, `current_node`, `run_id`, `workspace_volume`, `runs_volume`, `updated_at`, `exit_code`, and `gates`; unrecognized names are ignored.
- `fields.name`: on a missing registry entry, a non-null, truthy `name` supplies the new workflow's display name and a missing, `None`, or other falsey name falls back to `container_id[:12]`. On an existing registry entry, `name` behaves like any other recognized field and replaces the stored value only when it is not `None`.
- `fields.state`: when supplied and not `None`, replaces the workflow's [workflow state](workflow-state.md), allowing progress paths to mark `RUNNING`, blocked paths to mark `BLOCKED`, and exited paths to mark `FINISHED`.
- `fields.exit_code`: when supplied and not `None`, replaces the stored exit code; [receive exited push](../http/groom.md#receive-exited-push) passes an integer only after its own numeric check, so absent or non-numeric payload values preserve any existing code by passing `None`.

#### Return

- type: [workflow container](workflow-container.md)
- identity: the returned object is the same object stored in `WORKFLOWS[container_id]` after creation or update; callers may immediately mutate its `gates` map or inspect fields for rendering/notification text.

#### Effects

- Reads: the current `WORKFLOWS[container_id]` entry, when one exists.
- Creates: when no entry exists, constructs a new [workflow container](workflow-container.md) with `container_id` set to the supplied id and `name` set to the supplied truthy `fields["name"]` value when present, otherwise to `container_id[:12]`.
- Writes: stores a newly constructed workflow container in `WORKFLOWS[container_id]` before applying remaining field updates, making that object the authoritative registry entry for subsequent caller mutations.
- Consumes: on the creation path only, removes `name` from the local update set before the generic field loop so the constructor-chosen display name is not reassigned a second time.
- Updates: for every remaining `fields` item, assigns the value to the stored workflow container only when the value is not `None` and the workflow container exposes an attribute with the same field name.
- Updates: falsey but non-`None` values such as `""`, `0`, and `False` are real updates for recognized fields, which is why callers pass `None` when they want an absent payload value to preserve existing state.
- Preserves: every existing workflow-container field whose incoming value is `None`, whose field name is absent from the call, or whose field name is not part of the workflow-container contract.
- Preserves: open [gate info](gate-info.md) entries unless the caller mutates the returned workflow's `gates` map after upsert; [receive exited push](../http/groom.md#receive-exited-push) clears gates after this method returns rather than inside the upsert.
- Emits: the stored workflow container object after creation or mutation, allowing callers to add gate records, clear gates, rebuild gates from a sidecar snapshot, or inspect the resulting display name for notifications.
- Does not: normalize or truncate container ids, reject empty ids, validate field value types, coerce incoming values, update timestamps implicitly, clear gates, prune vanished containers, inspect Docker, register sidecar sockets, render HTML, broadcast dashboard fragments, write logs, sort or snapshot the registry, clone workflow records, acquire locks, or persist state outside process memory.

### method-reconcile-workflow-fleet

- sig: `async _reconcile() -> int`
- abstract: false
- raises: propagates discovery-scan, present-id lookup, and registry-prune exceptions from the called first-party discovery and state helpers.
- code: groom/groom/app.py::_reconcile
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers
- verify: groom/tests/test_app.py::test_refresh_skips_prune_when_docker_unavailable

Refreshes the registry from one Docker discovery pass. The method is shared by the manual [refresh workflow fleet](../http/groom.md#refresh-workflow-fleet) invocation and startup background discovery, and returns the number of workflow containers found by the scan before any stale-entry pruning decision.

#### Effects

- Reads: discoverable workflow containers from the Docker discovery layer via the [workflow discovery scan](workflow-discovery-scan.md), receiving only non-null workhorse-backed workflow records in Docker listing order.
- Writes: for each discovered [workflow container](workflow-container.md), assigns `WORKFLOWS[workflow.container_id] = workflow`, replacing any previous record under that id with the newly discovered snapshot.
- Reads: the current Docker container-id set via the discovery layer's [present container ids](workflow-discovery-scan.md#method-present-container-ids) lookup after discovered workflow records have been installed.
- Prunes: when the present-id lookup returns a set, delegates to [prune workflows](#method-prune-workflows) so registry entries whose containers no longer exist are removed and their per-gate locks are forgotten.
- Preserves: stale workflow entries when Docker present-id lookup returns `None`, so a transient Docker outage cannot wipe the visible fleet after a scan.
- Emits: integer count equal to `len(found)`, the number of workflow records returned by the scan, independent of how many existing entries were replaced or pruned.
- Does not: set or clear the scanning flag, broadcast dashboard HTML, inspect or render the dashboard shell itself, serialize concurrent refreshes, answer gate files, restart containers, register sidecars, write logs, or persist state outside memory.

### method-prune-workflows

- sig: `prune_workflows(present_ids: set[str]) -> list[str]`
- abstract: false
- raises: no domain-specific errors; ordinary mapping mutation errors would propagate.
- code: groom/groom/state.py::prune_workflows
- verify: groom/tests/test_state.py::test_prune_drops_absent_keeps_present
- verify: groom/tests/test_state.py::test_prune_empty_present_removes_everything
- verify: groom/tests/test_state.py::test_prune_also_forgets_gate_locks_of_removed
- verify: groom/tests/test_state.py::test_prune_is_noop_when_all_present
- verify: groom/tests/test_app.py::test_refresh_prunes_vanished_containers

Removes workflow registry entries whose container ids are absent from the caller-supplied present-id set, returns the removed ids, and clears any per-gate answer locks scoped to those removed containers so long-lived groom processes do not retain locks for vanished workers.

#### Effects

- Reads: the current `WORKFLOWS` keys and the supplied `present_ids` set.
- Computes: `removed` as every tracked container id that is not a member of `present_ids`, preserving the registry's current iteration order in the returned list.
- Deletes: each removed container id from `WORKFLOWS`, tolerating an already-missing entry without raising.
- Deletes: every per-gate lock whose internal key starts with `"{container_id}::"` for a removed container id, covering all gate-file paths under that vanished workflow.
- Preserves: workflow registry entries whose ids are present in `present_ids`, per-gate locks for preserved workflows, dashboard client queues, log entries, the scanning flag, sidecar connections, and any external Docker state.
- Emits: `list[str]` containing exactly the ids selected for removal.
- Does not: inspect Docker, decide whether pruning is safe during a Docker outage, render or broadcast dashboard fragments, answer or mutate gate files, restart containers, write logs, persist state, or mutate the caller's `present_ids` set.

## Algorithms

### algorithm-partial-event-upsert

- step: A push or sidecar applier normalizes or chooses the workflow container id before calling [upsert workflow](#method-upsert-workflow).
- step: If the id is absent, the registry creates a workflow container with that id and a display name from the supplied non-null `name` field or the first twelve id characters.
- step: The registry stores the new workflow before applying remaining field updates, so the same object is returned to the caller for any immediate gate-map mutation.
- step: For each supplied field, a non-`None` value whose name matches the workflow-container contract replaces the stored value.
- step: Omitted values, explicit `None` values, and unrecognized field names leave the stored workflow untouched.
- step: The caller decides whether to mutate gates, broadcast dashboard HTML, append logs, or perform Docker/sidecar work after the registry update.

### algorithm-exited-terminal-update

- step: The exited-push handler normalizes the payload's `container_id` to the first twelve string characters and stops before registry mutation when the result is empty.
- step: Before the terminal upsert, the handler gives the push-first volume metadata resolver a chance to hydrate missing workspace, runs, and workflow-type metadata for the normalized id.
- step: The handler calls [upsert workflow](#method-upsert-workflow) with optional identity fields, [workflow state](workflow-state.md) `finished`, and an `exit_code` value only when the payload's value is accepted as integer-like.
- step: The registry preserves existing identity and exit-code fields for omitted, `None`, or ordinary non-numeric values and creates a placeholder workflow when the normalized id was not already present.
- step: After upsert returns the stored workflow object, the exited-push handler clears that workflow's gate map in place because a terminal container cannot act on open gates.
- step: The handler broadcasts the refreshed dashboard shell and returns success without deleting the workflow entry; only [prune workflows](#method-prune-workflows) removes vanished containers after Docker presence is known.

### algorithm-discovery-reconciliation

- step: A startup or manual refresh path calls [reconcile workflow fleet](#method-reconcile-workflow-fleet).
- step: The reconciliation method reads the current Docker-backed [workflow discovery scan](workflow-discovery-scan.md) result.
- step: Each discovered workflow container replaces the registry value under its own container id.
- step: The method asks discovery for the set of present Docker container ids after replacement.
- step: When the present-id result is a set, [prune workflows](#method-prune-workflows) removes registry entries whose ids are absent and forgets their [per-gate answer lock](per-gate-answer-lock.md) entries.
- step: When the present-id result is `None`, pruning is skipped so a transient Docker outage cannot erase the visible fleet.
- step: The method returns the number of workflow containers discovered before pruning, leaving scanning flags and broadcasts to its caller.
