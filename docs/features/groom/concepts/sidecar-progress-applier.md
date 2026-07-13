---
type: concept
slug: sidecar-progress-applier
title: Sidecar progress applier
---
# Sidecar progress applier

The sidecar progress applier is the groom server layer that folds a connected sidecar's live `progress` [sidecar websocket frame](../sidecar-websocket-frame.md) into the process-local [workflow registry](workflow-registry.md) during the [run sidecar websocket session](../http/groom.md#run-sidecar-websocket-session) invocation. It marks the connected [workflow container](workflow-container.md) as [workflow state](workflow-state.md) `running`, optionally updates its current-node field through [upsert workflow](workflow-registry.md#method-upsert-workflow), and finishes by calling the [dashboard shell broadcaster](dashboard-shell-broadcaster.md) so browser dashboard tabs converge on the latest running-state snapshot.

- code: groom/groom/app.py::_apply_socket_progress

## Contract

- sig: `async _apply_socket_progress(container_id: str, data: dict) -> None`
- input: `container_id` is the non-empty, already-normalized workflow container id established by the sidecar websocket handler from the latest useful `hello`; this layer does not re-truncate, authenticate, or reject it.
- input: `data` is the decoded sidecar `progress` frame object; the layer reads only `data.get("current_node")` from it and ignores every other field.
- current-node rule: an absent or JSON `null` `current_node` preserves the workflow's existing current-node field through registry upsert semantics; any non-`None` value, including an empty string or non-string JSON value, is assigned to the workflow's `current_node` field as supplied.
- state rule: every call sets the workflow state to `RUNNING`, even when the progress frame omits `current_node` and even when the workflow previously had open gate records.
- gate rule: existing gate records are preserved; a progress frame is a liveness/current-node delta, not an authoritative gate snapshot and not a gate-clear signal.
- output: no return value; completion means registry mutation and shell broadcast have completed or an upstream exception has interrupted the operation.

## Inputs

### field: connected-container-id

- type: `str`
- default: none
- required: true
- source: the [websocket-sidecar](../http/groom.md#websocket-sidecar) session's registered sidecar connection, established by a prior useful `hello` frame.
- meaning: workflow registry key to update for this progress delta.
- constraints: accepted exactly as supplied by the caller; the applier does not normalize, truncate, authenticate, or reject empty strings.

### field: progress-current-node

- type: any JSON value
- default: `None` from `data.get("current_node")` when the key is absent or JSON `null`.
- required: false
- source: [sidecar websocket frame current-node](../sidecar-websocket-frame.md#field-current-node).
- meaning: optional current workhorse node to display for the connected workflow while marking it running.
- update rule: any value other than `None`, including `""`, `0`, `false`, an object, or a list, is assigned to the stored workflow's `current_node` field by registry upsert semantics.
- preserve rule: absent and JSON `null` values preserve the stored workflow's previous `current_node` field.

### field: progress-frame-extra-members

- type: arbitrary JSON object members
- default: ignored
- required: false
- meaning: any keys on the decoded progress frame other than `current_node`.
- consumer rule: this applier ignores them completely; identity, gate, terminal, RPC, and acknowledgement data have no progress-applier effect.

## Outputs

### field: return-value

- type: `None`
- default: none
- required: true
- meaning: the applier returns no domain object, status envelope, acknowledgement frame, or rendered fragment to its caller.

### field: dashboard-shell-broadcast

- type: [dashboard shell fragment](../dashboard-shell-fragment.md) side effect
- default: none
- required: true on successful completion after registry mutation
- sink: [dashboard shell broadcaster](dashboard-shell-broadcaster.md)
- meaning: connected dashboard tabs are offered a current inbox/list and status-bar shell after the running/current-node registry update.

## Routing Boundaries

- Caller: [run sidecar websocket session](../http/groom.md#run-sidecar-websocket-session) invokes this applier only for object frames whose `type` is `progress` and only after a prior useful `hello` has registered a sidecar connection.
- Precondition: a progress frame received before `hello` is ignored by the websocket session and never reaches this layer.
- Frame validation boundary: the applier does not inspect `data["type"]`, require `current_node`, or validate the value type; its entire frame-specific read is `data.get("current_node")`.
- Callee: the applier writes through [upsert workflow](workflow-registry.md#method-upsert-workflow), relying on registry partial-update semantics for placeholder creation and `None` preservation.
- Callee: the applier then calls [dashboard shell broadcaster](dashboard-shell-broadcaster.md) exactly once to publish the current shell state.

## Effects

- Creates or updates the workflow registry entry for `container_id` through [upsert workflow](workflow-registry.md#method-upsert-workflow), creating a placeholder workflow named from the normalized id if the registry entry is somehow absent after hello establishment.
- Writes [workflow state](workflow-state.md) `RUNNING` to the stored [workflow container](workflow-container.md).
- Writes the frame's non-`None` `current_node` value to the workflow container and preserves the previous current-node value when the frame omits it or supplies `null`.
- Broadcasts one out-of-band dashboard shell fragment through the [dashboard shell broadcaster](dashboard-shell-broadcaster.md) after the registry update, causing browser dashboard tabs to see the running state and current-node value.
- Does not register or unregister sidecar sockets, resolve pending RPCs, send acknowledgement frames, answer gate files, clear gate records, create [gate info](gate-info.md), persist workflow state outside memory, append answer logs, prune vanished workflows, inspect Docker volumes, emit a blocked notification script, read workspace files, or compute diffs.

## Methods

### method-apply-socket-progress

- sig: `async _apply_socket_progress(container_id: str, data: dict) -> None`
- abstract: false
- raises: propagates workflow-upsert, renderer, or broadcast exceptions; absent `current_node`, JSON `null` current nodes, empty strings, non-string current-node values, and extra frame fields are handled as ordinary inputs.
- code: groom/groom/app.py::_apply_socket_progress

Fold one connected sidecar `progress` frame for one already accepted sidecar websocket into the visible workflow fleet.

#### Effects

- Reads: the `current_node` member from the decoded [sidecar websocket frame](../sidecar-websocket-frame.md) using missing-field default `None`.
- Calls: [workflow registry upsert](workflow-registry.md#method-upsert-workflow) with the connected container id, the raw `current_node` value, and [workflow state](workflow-state.md) `RUNNING`.
- Creates: a placeholder [workflow container](workflow-container.md) named from the normalized container id if the registry entry is absent despite the preceding hello requirement.
- Writes: the workflow container's state to `RUNNING` on every call.
- Writes: the workflow container's current-node field only when the frame value is not `None`; omitted and JSON `null` values preserve the previous current-node field through registry upsert semantics.
- Preserves: workflow display identity, repository identity, workflow type, workspace and runs volumes, run id, exit code, existing gate map, answer logs, dashboard client registrations, and sidecar connection registration.
- Calls: [dashboard shell broadcaster](dashboard-shell-broadcaster.md) after the registry mutation so browser dashboards receive the updated running/current-node shell.

## Algorithms

### algorithm-sidecar-progress-application

- step: Accept the caller-supplied container id as the authoritative workflow key; the websocket session has already established it from a useful sidecar hello and scoped this progress frame to that registered connection.
- step: Read `current_node` directly from the decoded progress frame, producing `None` when the key is absent.
- step: Upsert the workflow registry entry with state `RUNNING` and the raw current-node value.
- step: Let registry partial-update semantics create a missing workflow placeholder if needed, preserve every omitted or `None` field, and assign any non-`None` current-node value exactly as supplied.
- step: Leave all existing gate records untouched because a progress frame is a liveness/current-node delta rather than a gate snapshot or unblock signal.
- step: Broadcast the current dashboard shell so connected browser dashboards converge on the updated running state and current-node text.

## Failure Semantics

- Workflow-upsert, renderer, or broadcast exceptions are not converted into a progress-specific result; they propagate to the websocket session handler after any earlier registry mutation has already happened.
- If broadcasting fails after the workflow has been marked running, the in-memory workflow state remains updated while some or all connected browser clients may not have received the corresponding shell fragment.
- The layer does not verify that `data.type` is `progress`; frame routing is owned by the sidecar websocket session handler, so a direct caller with another frame shape would still apply the same current-node/default rules.
