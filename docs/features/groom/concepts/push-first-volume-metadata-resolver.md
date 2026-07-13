---
type: concept
slug: push-first-volume-metadata-resolver
title: Push-first volume metadata resolver
---
# Push-first volume metadata resolver

The push-first volume metadata resolver fills Docker-derived volume fields for a [workflow container](workflow-container.md) that reaches groom through a residual push before a full discovery scan has populated the [workflow registry](workflow-registry.md). The [receive progress push](../http/groom.md#receive-progress-push), [receive blocked push](../http/groom.md#receive-blocked-push), [receive exited push](../http/groom.md#receive-exited-push), and [sidecar hello applier](sidecar-hello-applier.md) paths use it before applying visible state from a first push or sidecar snapshot that lacks Docker-level volume names. It delegates raw Docker metadata retrieval to the [Docker inspection reader](docker-inspection-reader.md), consumes the resulting [Docker inspect container object](../docker-inspect-container-object.md) through the [workflow-container conversion](../docker-inspect-container-object.md#consumer-workflow-container-conversion) implemented by [method-container-from-inspect](workflow-discovery-scan.md#method-container-from-inspect), and writes back through the [workflow registry](workflow-registry.md#method-upsert-workflow) partial-update rule.

- code: groom/groom/app.py::_ensure_volumes
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code
- refs: [receive progress push](../http/groom.md#receive-progress-push), [receive blocked push](../http/groom.md#receive-blocked-push), [receive exited push](../http/groom.md#receive-exited-push), [sidecar hello applier](sidecar-hello-applier.md), [Docker inspection reader](docker-inspection-reader.md), [Docker inspect container object](../docker-inspect-container-object.md), [workflow-container conversion](../docker-inspect-container-object.md#consumer-workflow-container-conversion), [method-container-from-inspect](workflow-discovery-scan.md#method-container-from-inspect), [workflow container](workflow-container.md), [workflow registry upsert](workflow-registry.md#method-upsert-workflow)

## Contract

- input: `container_id` string, required; callers pass the already normalized workflow container id used as the registry key.
- output: no return value; all successful work is represented as in-memory registry mutation.
- idempotency: if the registry already contains a workflow record for `container_id` and its `workspace_volume` field is non-empty, the resolver returns without contacting Docker or changing any registry field.
- completeness boundary: the short-circuit is based only on `workspace_volume`; a workflow that already has a non-empty workspace volume is not checked for missing `runs_volume` or `workflow_type` by this resolver.
- missing-record: an absent registry entry does not block resolution; successful inspection creates or updates the registry record through the normal workflow upsert path.
- missing-inspection: when Docker inspection returns no metadata for the id, the resolver returns without creating or updating the registry entry and lets the caller continue its own push handling.
- thread boundary: Docker inspection is run off the async event loop; the resolver awaits that worker-thread read before converting or mutating registry state.
- concurrency: no registry lock, retry loop, deduplication of simultaneous first-sight calls, or cross-process coordination is provided.
- call sites: [receive progress push](../http/groom.md#receive-progress-push), [receive blocked push](../http/groom.md#receive-blocked-push), and [receive exited push](../http/groom.md#receive-exited-push) call the resolver after container-id validation and before applying their event-specific registry mutation; [sidecar hello applier](sidecar-hello-applier.md) calls it before folding identity and snapshot data into the registry.
- input trust: the resolver does not normalize, truncate, validate, or classify the supplied id; callers own the id boundary and the Docker inspection reader decides whether the id resolves to metadata.
- conversion scope: the resolver accepts whatever workflow-container conversion emits, including an empty workspace volume, empty runs volume, empty workflow type, or non-workhorse-shaped Docker inspect object; it does not require the inspect object to pass the [workhorse-container classifier](workflow-discovery-scan.md#method-classify-workhorse-container) before using the converted metadata.
- update scope: only `workspace_volume`, `runs_volume`, and `workflow_type` are supplied to the registry upsert, so name, repository identity, lifecycle state, current node, run id, exit code, gates, and timestamp are never replaced by this resolver.
- empty-value rule: converted empty strings for `workspace_volume`, `runs_volume`, or `workflow_type` are still non-null values for the registry upsert, so they may be assigned on a newly created record or replace those fields on an existing record that lacked `workspace_volume` and therefore did not short-circuit.
- observability: normal completion emits no response fragment, log event, notification script, or return payload; downstream endpoint responses and broadcasts come from the caller after its own mutation succeeds.

## Effects

- Reads: the current `state.WORKFLOWS` entry for `container_id`, if one exists.
- Skips: all Docker and registry work when the existing workflow already has a non-empty `workspace_volume`.
- Calls: the [Docker inspection reader](docker-inspection-reader.md) for `container_id` when the workflow is absent or lacks a workspace volume.
- Derives: a temporary [workflow container](workflow-container.md) view from the [Docker inspect container object](../docker-inspect-container-object.md), using only the discovered `workspace_volume`, `runs_volume`, and `workflow_type` fields for this resolver's write.
- Writes: upserts the registry entry keyed by `container_id` with `workspace_volume`, `runs_volume`, and `workflow_type` from the inspected container when inspection succeeds, even when one or more converted values are empty strings.
- Creates: a new registry entry through upsert when inspection succeeds and the id was absent, using the supplied id as the registry key and display-name fallback because this resolver does not pass a `name` field.
- Preserves: existing workflow name, repository identity, branch, current node, lifecycle state, run id, exit code, gate map, and update timestamp unless the normal upsert semantics receive a non-null replacement for one of the three metadata fields this resolver supplies.
- Does not: broadcast dashboard HTML, render fragments, answer or clear gates, mark workflow state, prune vanished containers, register sidecar sockets, read workspace files, compute diffs, or persist data outside the groom process.

## Methods

### method-ensure-volumes

- sig: `async _ensure_volumes(container_id: str) -> None`
- abstract: false
- raises: propagates process-launch or timeout failures from Docker inspection, valid-JSON shape errors from the inspection reader, workflow-container conversion errors, thread handoff failures, or registry-upsert assignment errors; Docker command failure, invalid JSON, and empty inspect output are not raised and are represented by no mutation.
- code: groom/groom/app.py::_ensure_volumes
- verify: groom/tests/test_app.py::test_push_exited_marks_finished_clears_gates_and_records_code

Ensure that the workflow registry entry for one already-normalized container id has Docker volume metadata before a push-first or sidecar-first caller continues with its own state update.

#### Effects

- Reads: `state.WORKFLOWS[container_id]` when present.
- Returns: immediately when the entry exists and its `workspace_volume` is non-empty.
- Calls: [Docker inspection reader](docker-inspection-reader.md) with the supplied container id when the entry is absent or lacks `workspace_volume`.
- Returns: without mutation when the inspection reader returns no metadata.
- Calls: [workflow-container conversion](../docker-inspect-container-object.md#consumer-workflow-container-conversion) with the raw inspection object when metadata exists.
- Calls: [workflow registry upsert](workflow-registry.md#method-upsert-workflow) with the supplied id plus `workspace_volume`, `runs_volume`, and `workflow_type` from the converted workflow container.
- Creates: a registry entry named from the supplied id when the id was not present before this resolver and Docker inspection returned metadata, because no display name is passed to upsert.
- Preserves: all registry fields that are not one of the three supplied metadata fields, subject to the registry upsert's non-null update rule.
- May replace: existing `runs_volume` or `workflow_type` values with empty strings when the existing record lacks `workspace_volume`, the inspect object omits the corresponding metadata, and the registry upsert receives those empty converted values.

## Algorithms

### algorithm-push-first-volume-hydration

- step: Receive a container id that the caller has already chosen as the workflow registry key.
- step: Look up the current workflow registry entry for that id.
- step: If an entry exists and already has a non-empty workspace-volume field, stop; the resolver treats the existing metadata as authoritative enough for downstream volume operations.
- step: Ask the Docker inspection reader for raw inspect metadata for the same id on a worker thread so the asynchronous handler does not perform the blocking Docker call on the event loop.
- step: If Docker returns no usable inspect object, stop without creating a workflow record; the caller continues its own event handling with whatever payload data it has.
- step: Convert the raw inspect object into a transient workflow-container view using the shared Docker-inspect conversion contract, without first applying the workhorse-container classifier or requiring `/workflow`, `/runs`, and `/workspace` mounts.
- step: Upsert the registry entry under the caller's id with only the converted workspace volume, runs volume, and workflow type; empty converted strings are still assigned because the registry ignores only `None` values.
- step: Return without broadcasting or responding; the caller remains responsible for any visible state transition, gate mutation, websocket broadcast, or HTTP response.

## Failure Semantics

- docker-command-failure: a Docker inspect command that returns a non-zero status is treated as missing inspection data and produces no mutation.
- invalid-json: invalid Docker inspect JSON is treated as missing inspection data and produces no mutation.
- empty-inspect-output: a successful Docker inspect command whose parsed JSON array is empty is treated as missing inspection data and produces no mutation.
- exceptions: process-launch failures, subprocess timeouts, truthy valid-JSON values with unsupported shape, conversion errors, and registry-upsert assignment errors are not converted into endpoint-specific error bodies by this resolver; they propagate to the caller.
