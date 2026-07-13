---
type: concept
slug: workflow-gate-clearer
title: Workflow gate clearer
---
# Workflow gate clearer

Workflow gate clearer is the [Groom state module](groom-state-module.md) operation that removes one answered [gate info](gate-info.md) entry from one tracked [workflow container](workflow-container.md) in the [workflow registry](workflow-registry.md). The [gate-answering layer](gate-answering-layer.md) calls it only after the matching operator gate context file has been successfully rewritten to `STATUS: ANSWERED`, so failed, stale, or unwritable answer attempts leave the visible in-memory gate untouched. It is intentionally narrower than the [per-gate answer lock](per-gate-answer-lock.md): callers serialize and durably answer a gate first, then use this operation only to update groom's visible process-local state.

- code: groom/groom/state.py::clear_gate
- verify: groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running

## Contract

- purpose: remove exactly one open gate from groom's process-local workflow state after durable answer-file write success, so the dashboard no longer renders an answer form for that gate while waiting for the workflow's next push or shell refresh.
- caller: [gate-answering layer](gate-answering-layer.md) invokes this operation with the submitted workflow container id and gate file path after a successful workspace-volume file write.
- API: synchronous helper with no return payload; completion means only that the local no-op-or-delete attempt finished.
- input: `container_id` identifies the workflow registry entry to mutate; it is used as supplied and is not normalized or validated by this operation.
- input: `file_path` identifies the gate map entry to remove from the selected workflow container; it is used as supplied and is not path-normalized or validated by this operation.
- storage shape: the selected workflow's gate map is a mutable `dict[str, GateInfo]` keyed by exact gate file path strings; this operation deletes at most one key from that map and never rewrites the stored [gate info](gate-info.md) value before deletion.
- data dependency: the selected registry value must expose a mutable `gates` mapping compatible with the [workflow container](workflow-container.md) contract; an incompatible object is outside the supported state shape and may fail during mutation.
- lookup: reads `WORKFLOWS.get(container_id)` from the [workflow registry](workflow-registry.md), so a missing workflow is observed as absent data rather than creating or upserting a registry entry.
- mutation: when the workflow exists, removes the gate stored at `workflow.gates[file_path]` if present, using exact key equality on the supplied `file_path` and mutating the stored [workflow container](workflow-container.md) object in place.
- missing workflow behavior: when the workflow registry has no entry for `container_id`, returns without creating a workflow, raising, or mutating any other state.
- missing gate behavior: when the workflow exists but has no gate under `file_path`, leaves the workflow unchanged and returns without raising.
- result: emits no status object or boolean; callers cannot distinguish removed, already absent, and missing-workflow outcomes from the return value alone.
- idempotence: repeated calls with the same `(container_id, file_path)` pair are safe after the first removal because absent workflows and absent gate keys are tolerated.
- ordering: callers that need answer-file durability or per-gate serialization must perform those steps before calling; this operation does not acquire the [per-gate answer lock](per-gate-answer-lock.md) itself.
- scope: mutates only the in-memory gate map on the selected workflow container in the current groom process.
- non-effect: does not write the gate file, mark workflow state as running or finished, broadcast dashboard HTML, append event logs, inspect Docker, restart containers, prune vanished workflows, clear per-gate locks, or persist state outside memory.

## Methods

### method-clear-gate

- sig: `clear_gate(container_id: str, file_path: str) -> None`
- abstract: false
- raises: no domain-specific errors; ordinary mutation errors from an incompatible workflow object or gate map would propagate.
- returns: `None`
- code: groom/groom/state.py::clear_gate
- verify: groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running

Removes the gate entry keyed by `file_path` from the workflow stored under `container_id`, if both exist.

#### Parameters

- `container_id`: required `str` opaque workflow-registry key with no default. The method uses exact string equality and does not trim, truncate, reject empty values, or inspect Docker for the container.
- `file_path`: required `str` gate-map key with no default. The method uses exact string equality against the selected workflow container's `gates` map and does not normalize paths, reject absolute paths, or check the backing workspace file.

#### Return

- type: `None`
- meaning: the method has no distinguishable success, already-cleared, or missing-workflow result channel.

#### Effects

- Reads: the current `WORKFLOWS[container_id]` entry from the process-local [workflow registry](workflow-registry.md).
- Reads: the selected workflow container's `gates` mapping only after the workflow lookup succeeds.
- Deletes: at most one `file_path` entry from the selected workflow container's `gates` map when the workflow exists and the key is present.
- Tolerates: absent workflow records and absent gate keys by completing without mutation or error.
- Preserves: every other gate on the same workflow, every gate on other workflows, workflow identity and metadata fields, per-gate locks, log entries, dashboard websocket clients, and external Docker/container state.
- Emits: no return value; success, missing workflow, and missing gate all complete as `None`.
- Does not: validate identifiers, normalize file paths, acquire locks, touch workspace files, update workflow lifecycle state, render HTML, broadcast websocket fragments, or remove stale registry entries.

## Algorithm

- step: Look up the current workflow container in the process-local [workflow registry](workflow-registry.md) by the supplied `container_id`.
- step: If the lookup returns no workflow, stop immediately with no mutation and no error.
- step: If a workflow exists, inspect that workflow's mutable `gates` mapping and remove the exact `file_path` key when present.
- step: If the workflow has no matching gate key, leave the gates map unchanged and still complete normally.
- step: Return `None` for every path through the operation.
