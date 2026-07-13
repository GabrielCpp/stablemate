---
type: concept
slug: sidecar-hello-applier
title: Sidecar hello applier
---
# Sidecar hello applier

The sidecar hello applier is the groom server layer that folds a connected sidecar's useful `hello` [sidecar websocket frame](../sidecar-websocket-frame.md) into the process-local [workflow registry](workflow-registry.md) during the [run sidecar websocket session](../http/groom.md#run-sidecar-websocket-session) invocation. It treats the embedded [sidecar snapshot data](../sidecar-snapshot-data.md) as authoritative for the connected container's current gates, uses the [push-first volume metadata resolver](push-first-volume-metadata-resolver.md) before applying workflow identity, writes [workflow container](workflow-container.md) state through [upsert workflow](workflow-registry.md#method-upsert-workflow), creates [gate info](gate-info.md) records for retained snapshot gates, and finishes by calling the [dashboard shell broadcaster](dashboard-shell-broadcaster.md).

- code: groom/groom/app.py::_apply_hello
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate
- verify: groom/tests/test_app.py::test_apply_hello_running_when_no_gates
- verify: groom/tests/test_app.py::test_apply_hello_finished_when_terminal
- verify: groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively

## Contract

- sig: `async _apply_hello(container_id: str, data: dict) -> None`
- input: `container_id` is the non-empty, already-normalized workflow container id established by the sidecar websocket handler from `identity.container_id`; this layer does not re-truncate or reject it.
- input: `data` is the decoded sidecar `hello` frame object; missing or falsey `identity` and `snapshot` values are treated as empty objects.
- nested-object rule: truthy `identity` and `snapshot` values must expose object-style `get` lookup; this layer tolerates absent or falsey nested objects but does not coerce truthy non-mapping values.
- identity fields: `identity.name`, `identity.repo_name`, and `identity.repo_branch` are passed to workflow upsert as optional replacements; omitted or `None` values preserve the current workflow field through the registry upsert semantics.
- current-node rule: a truthy `snapshot.current_node` replaces the workflow's current node; a falsey or absent value preserves the existing current node.
- gate rule: every useful hello clears the workflow's existing gate map before applying snapshot gates, so reconnect snapshots replace stale host-side gates rather than merging with them.
- retained gate rule: each `snapshot.gates[]` entry whose string-normalized `file_path` is non-empty creates or replaces one gate record keyed by that file path, with `workflow_id` set to `container_id`, `file_path` set to the normalized path, and `question` set to `str(gate.get("question", ""))`.
- gate-entry shape rule: retained gate candidates are expected to be mapping-like objects with `get`; entries without that interface are not skipped by this layer and fail the hello application if iterated.
- state rule: a truthy `snapshot.terminal` marks the workflow `FINISHED`; otherwise any retained gate marks it `BLOCKED`, and no retained gates marks it `RUNNING`.
- output: no return value; completion means metadata resolution, registry mutation, authoritative gate rebuilding, state selection, and shell broadcast have completed or an upstream exception has interrupted the operation.

## Effects

- Resolves Docker-derived workspace/runs volume metadata for the normalized container id through the [push-first volume metadata resolver](push-first-volume-metadata-resolver.md) before applying the hello-specific identity fields.
- Creates or updates the workflow registry entry through [upsert workflow](workflow-registry.md#method-upsert-workflow), preserving existing workflow fields for identity values omitted by the hello frame.
- Mutates the returned [workflow container](workflow-container.md) in place by optionally updating `current_node`, clearing `gates`, adding retained [gate info](gate-info.md) records, and setting [workflow state](workflow-state.md) according to the terminal/gate rules.
- Broadcasts one out-of-band dashboard shell fragment through the [dashboard shell broadcaster](dashboard-shell-broadcaster.md) after the registry has been mutated.
- Does not register or unregister sidecar sockets, resolve pending RPCs, send acknowledgement frames, answer gate files, persist workflow state outside memory, append answer logs, prune vanished workflows, read workspace files, compute diffs, or emit a blocked notification script.

## Methods

### method-apply-hello

- sig: `async _apply_hello(container_id: str, data: dict) -> None`
- abstract: false
- raises: propagates metadata-resolution, workflow-upsert, gate-record construction, renderer, broadcast, truthy non-mapping identity/snapshot, malformed non-iterable gate-list, or malformed iterated gate-entry exceptions; missing identity, missing snapshot, empty gate paths, and falsey snapshot fields are handled as ordinary inputs.
- code: groom/groom/app.py::_apply_hello
- verify: groom/tests/test_app.py::test_apply_hello_marks_blocked_with_gate
- verify: groom/tests/test_app.py::test_apply_hello_running_when_no_gates
- verify: groom/tests/test_app.py::test_apply_hello_finished_when_terminal
- verify: groom/tests/test_app.py::test_apply_hello_reconnect_rebuilds_gates_authoritatively

Fold one useful sidecar `hello` frame for one already accepted sidecar websocket into the visible workflow fleet.

#### Effects

- Reads: `identity` and `snapshot` from the decoded [sidecar websocket frame](../sidecar-websocket-frame.md), replacing missing or falsey objects with empty objects.
- Calls: [push-first volume metadata resolver](push-first-volume-metadata-resolver.md) for the normalized container id before any hello-specific registry upsert.
- Calls: [workflow registry upsert](workflow-registry.md#method-upsert-workflow) with `name`, `repo_name`, and `repo_branch` from the hello identity.
- Writes: the returned [workflow container](workflow-container.md)'s current node only when `snapshot.current_node` is truthy.
- Writes: clears the workflow container's gate map before applying any snapshot gate entries.
- Writes: for each retained snapshot gate with a non-empty string-normalized file path, stores a [gate info](gate-info.md) record keyed by that path with the connected container id and string-normalized question.
- Writes: sets [workflow state](workflow-state.md) to `FINISHED` when `snapshot.terminal` is truthy, otherwise to `BLOCKED` when any gate remains or `RUNNING` when none remain.
- Calls: [dashboard shell broadcaster](dashboard-shell-broadcaster.md) after the registry mutation so browser dashboards receive the rebuilt shell state.

## Algorithms

### algorithm-sidecar-hello-application

- step: Accept the caller-supplied container id as the authoritative workflow key; the websocket session has already derived and validated it from the sidecar identity.
- step: Read `identity` and `snapshot` from the decoded hello frame, treating missing or falsey values as empty mappings for this application pass.
- step: Ensure Docker-derived workspace and runs volume metadata exists when Docker inspection can provide it, so later answer and fallback paths have volume names even when the sidecar connected before discovery.
- step: Upsert the workflow registry entry with the optional identity fields carried by the hello frame.
- step: If the snapshot carries a truthy current node, replace the workflow container's current node with that value; otherwise leave the previous current node untouched.
- step: Clear all existing gates for the workflow because a useful hello is a full current-gate advertisement, not a delta.
- step: If the snapshot carries a truthy terminal marker, mark the workflow finished and retain no snapshot gates.
- step: Otherwise iterate the advertised gates, skip entries whose string-normalized file path is empty, and store one gate record per retained path.
- step: Mark the non-terminal workflow blocked when at least one gate remains, or running when the rebuilt gate map is empty.
- step: Broadcast the current dashboard shell so connected browser dashboards converge on the rebuilt workflow state.

## Failure Semantics

- Metadata-resolution, workflow-upsert, gate-record construction, renderer, broadcast, truthy non-mapping identity/snapshot, or malformed gate-entry exceptions are not converted into a hello-specific result; they propagate to the websocket session handler after any earlier mutations have already happened.
- Empty or malformed `snapshot.gates` values that are falsey are treated as no retained gates; non-empty non-iterable values and iterated entries without object-style `get` lookup are not separately guarded by this layer.
- A gate entry with an empty string-normalized file path is skipped without failing the hello and without creating a placeholder gate.
