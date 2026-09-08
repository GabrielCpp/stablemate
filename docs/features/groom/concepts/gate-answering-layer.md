---
type: concept
slug: gate-answering-layer
title: Gate-answering layer
---
# Gate-answering layer

Gate-answering layer is the asynchronous service operation that applies one submitted [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) to one live [gate info](gate-info.md) on a [workflow container](workflow-container.md). It reads the [operator gate context file](../operator-gate-context-file.md) through the [workspace volume file-content reader](workspace-volume-file-content-reader.md) and rewrites it through the [workspace volume file writer](workspace-volume-file-writer.md) inside the workflow workspace volume while holding the matching [per-gate answer lock](per-gate-answer-lock.md), returns an [answer result](../answer-result.md) for the dashboard command handler, clears the matching in-memory gate through the [workflow gate clearer](workflow-gate-clearer.md) after a successful write, and starts the workflow container through the [stopped container start fallback](stopped-container-start-fallback.md) only when the [container running-state check](container-running-state-check.md) reports that the container is not already running.

The operation's rejection, in-place answer, stopped-container restart, and missing-volume behavior are covered by `groom/tests/test_gates.py::test_answer_gate_rejects_when_already_answered`, `groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running`, `groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped`, and `groom/tests/test_gates.py::test_answer_gate_reports_missing_workspace_volume`.

- code: groom/groom/gates.py::answer_gate

## Contract

- purpose: accept one operator answer for one gate file and make the in-container wait script observe `STATUS: ANSWERED` without requiring a container restart on the normal path.
- caller: the dashboard websocket command handler calls this operation after normalizing `workflow_id`, `file_path`, and `answer` from a [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) and resolving the selected workflow's current workspace volume.
- input: `container_id` is the workflow container id used for the per-gate lock, in-memory gate removal, running-state check, and fallback `docker start` target.
- input: `file_path` is the volume-relative [operator gate context file](../operator-gate-context-file.md) path; it scopes the lock and state removal with `container_id` and is passed to Docker volume read/write operations.
- input: `answer` is the operator-authored answer text; surrounding whitespace is stripped before appending, and a blank answer still flips the gate status without appending an answer paragraph.
- input: `workspace_volume` is the Docker workspace volume name that contains the gate file; an empty value rejects the attempt before any lock, file read, file write, state mutation, running-state check, or restart attempt.
- consistency: workspace-volume — `answer_gate` returns `AnswerResult(ok=False, message="unknown workspace volume for this container")` when `workspace_volume` is empty.
- verify: json_path(path="$.ok", equals=false)
- verify: json_path(path="$.message", equals="unknown workspace volume for this container")
- concurrency: per-gate-answer-lock — one [per-gate answer lock](per-gate-answer-lock.md) is shared per `(container_id, file_path)` pair, so simultaneous browser submissions for different gates can proceed independently, while submissions for the same gate serialize from the file read through any stopped-container restart fallback.
- lock lookup effect: before reading the gate file, the operation asks the per-gate lock registry for the lock keyed by the submitted `container_id` and `file_path`; that lookup may create and retain a new unlocked process-local lock when this pair has not been answered or pruned before.
- lock lifecycle: the operation releases the per-gate lock only when returning its [answer result](../answer-result.md) or propagating an exception; it never deletes the retained lock after success or rejection, and workflow pruning is the cleanup path for locks belonging to removed containers.
- stale guard: the gate file is read again while holding the per-gate lock, and the answer is rejected unless the current file status is exactly `AWAITING_OPERATOR` after status normalization.
- write effect: a successful write persists the [operator gate context file answer applier](../operator-gate-context-file.md#method-apply-answer) output through the [workspace volume file writer](workspace-volume-file-writer.md): at most the first matched `STATUS:` line becomes `STATUS: ANSWERED`, the stripped answer is appended as a trailing paragraph only when non-blank, and the whole updated text is streamed to the same workspace volume path as the replacement file content.
- state effect: after the file write succeeds, the matching in-memory [gate info](gate-info.md) entry is removed through the [workflow gate clearer](workflow-gate-clearer.md) from the selected [workflow container](workflow-container.md) if that workflow is still present in the process registry; a missing workflow or already-absent gate is tolerated and does not change the answer result.
- consistency: in-memory-gate-entry — after a successful answer-file write, the [workflow gate clearer](workflow-gate-clearer.md) removes a present in-memory gate entry for `(container_id, file_path)` from the selected [workflow container](workflow-container.md).
- verify: removed(subject="the selected workflow's in-memory gate entry for (container_id, file_path)")
- wake effect: after clearing the in-memory gate, the operation asks the [container running-state check](container-running-state-check.md) whether the container is running. A running container needs no restart because its wait script wakes from the changed file.
- fallback effect: when the container is not running after a successful write, the operation attempts one `docker start` for `container_id` through the [stopped container start fallback](stopped-container-start-fallback.md); this is only the stopped-container fallback, not the common path.
- output: returns one [answer result](../answer-result.md) for every attempted answer, with `ok=false` when the attempt could not be applied and `ok=true` once the answer file write has succeeded.
- failure ordering: an empty `workspace_volume` is rejected before acquiring a gate lock; a missing gate file is rejected after the locked read; a non-awaiting status is rejected after the locked status check; a failed write is rejected after answer text construction but before in-memory gate removal.
- exception behavior: unsafe or traversal-like `file_path` values are rejected by the Docker volume file helpers and propagate as exceptions rather than being converted to an [answer result](../answer-result.md); subprocess timeouts, process-launch errors, and unexpected Docker helper exceptions also propagate to the caller, and completed earlier side effects such as a successful answer write or in-memory gate clear are not rolled back.
- non-effect: does not broadcast dashboard HTML, append an answer log entry, change workflow state from blocked to running, validate websocket command shape, render forms, scan Docker containers, or persist any database record; those effects belong to the caller or adjacent layers.

## Return Outcomes

The `answer_gate` implementation returns `AnswerResult(ok=False,
message="unknown workspace volume for this container")` for an empty `workspace_volume`,
before requesting a lock or performing Docker, state, or restart work. A locked read with no file
text produces `AnswerResult(ok=False, message="gate file not found")`, without building answer
text, writing the file, or clearing the in-memory gate. A readable file whose current status is not
`AWAITING_OPERATOR` produces `AnswerResult(ok=False, message="already answered in another tab")`;
it likewise leaves the file and in-memory gate unchanged. If the writer reports failure after the
updated text is built, the result is `AnswerResult(ok=False, message="failed to write answer")`,
before the gate clear or container-state check.

After a successful write and gate-clear request, a running workflow container results in
`AnswerResult(ok=True, message="answered")`. A stopped container whose fallback start succeeds
results in `AnswerResult(ok=True, message="answered and restarted")`; a failed fallback start
instead produces `AnswerResult(ok=True, message="answer written but restart failed — start the
container manually")`, while the persisted answer remains accepted.

## Methods

### answer-gate

- sig: `async answer_gate(container_id: str, file_path: str, answer: str, *, workspace_volume: str) -> AnswerResult`
- abstract: false
- raises: Propagates exceptions from the underlying Docker volume and container-status helpers.
- returns: Represents expected domain failures as `AnswerResult(ok=False, message=...)`.
- verify: json_path(path="$.ok", equals=false)
- returns: an [answer result](../answer-result.md) indicating whether the answer was rejected, accepted with the container already running, accepted with a stopped-container restart, or accepted while the restart fallback failed.

Applies one operator answer to one awaiting gate file, clears the corresponding in-memory gate after a successful write, and optionally starts a stopped workflow container.

## Algorithm

The operation first obtains the process-local lock keyed by `container_id` and `file_path`. When
the pair has no existing lock, the per-gate lock registry creates and retains an unlocked lock for
later same-pair answer attempts.

Holding the returned lock guards every subsequent step: the gate-file read, the stale-status
check, the answer write, the in-memory gate clear, the running-state check, and any restart
fallback. The operation reads the current gate file text from `workspace_volume` and `file_path`
using the [workspace volume file-content reader](workspace-volume-file-content-reader.md); if the
file cannot be read, it returns `ok=false` with message `gate file not found`. It then classifies
the current file with [operator gate context file status check](../operator-gate-context-file.md#method-is-awaiting):
if the normalized status token is not `AWAITING_OPERATOR`, it returns `ok=false` with message
`already answered in another tab`.

Otherwise it builds the answered gate text with the [operator gate context file answer applier](../operator-gate-context-file.md#method-apply-answer)
— replacing at most the first matched status line with `STATUS: ANSWERED`, stripping the submitted
answer, appending it only when non-empty, and otherwise preserving the status-updated file text
without trimming trailing content — and writes that text back to the same workspace volume and
file path using the [workspace volume file writer](workspace-volume-file-writer.md), which applies
the shared safe relative-path guard before starting the write process and reports success from the
Docker copy process exit code. If the writer returns `false`, the operation returns `ok=false` with
message `failed to write answer` before clearing in-memory gate state or checking container
liveness.

After a successful write, the operation asks the [workflow gate clearer](workflow-gate-clearer.md)
to remove the exact `file_path` key from the in-memory gates map for `container_id`; if the
workflow or gate is already absent, the clear completes without raising and the answer path
continues. Still holding the per-gate answer lock, it then asks the [container running-state
check](container-running-state-check.md) whether the workflow container is running. A running
container yields `ok=true` with message `answered`. A stopped container whose [stopped container
start fallback](stopped-container-start-fallback.md) succeeds yields `ok=true` with message
`answered and restarted`; a stopped container whose fallback fails yields `ok=true` with message
`answer written but restart failed — start the container manually`. Every return path releases the
lock while leaving its registry entry retained.

## Collaborators

- uses: [per-gate answer lock](per-gate-answer-lock.md) supplies the per-gate asynchronous lock.
- uses: [workspace volume file-content reader](workspace-volume-file-content-reader.md) reads the current gate file text before the stale-status check.
- uses: [operator gate context file status check](../operator-gate-context-file.md#method-is-awaiting) checks whether the current file status is still `AWAITING_OPERATOR`.
- uses: [operator gate context file answer applier](../operator-gate-context-file.md#method-apply-answer) builds the updated gate file content.
- uses: [workspace volume file writer](workspace-volume-file-writer.md) writes the updated file into the workspace volume.
- uses: [container running-state check](container-running-state-check.md) distinguishes the normal in-place wake path from the stopped-container fallback.
- uses: [stopped container start fallback](stopped-container-start-fallback.md) performs the stopped-container Docker start attempt after a successful file write.
- uses: [answer result](../answer-result.md) is the success/failure value returned to the dashboard websocket command handler.
