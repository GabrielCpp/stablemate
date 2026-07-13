---
type: concept
slug: stopped-container-start-fallback
title: Stopped container start fallback
---
# Stopped container start fallback

Stopped container start fallback is Groom's post-answer recovery path for a workflow container that is no longer running after the [gate-answering layer](gate-answering-layer.md) has successfully written an operator answer and cleared the in-memory [gate info](gate-info.md). The [container running-state check](container-running-state-check.md) selects this path by returning `False`; the fallback performs exactly one Docker `start` attempt through the [Docker subprocess runner](docker-subprocess-runner.md) owned by the [Groom Docker I/O module](groom-docker-io-module.md), then reports the outcome through an [answer result](../answer-result.md). It is intentionally narrower than workflow recreation: removed containers, compose services, missing environment, and cached launch metadata are outside this fallback.

- code: groom/groom/docker_io.py::docker_start
- verify: groom/tests/test_gates.py::test_answer_gate_writes_answer_no_restart_when_still_running
- verify: groom/tests/test_gates.py::test_answer_gate_restarts_when_container_stopped
- refs: [Gate-answering layer](gate-answering-layer.md), [Container running-state check](container-running-state-check.md), [Docker subprocess runner](docker-subprocess-runner.md), [Groom Docker I/O module](groom-docker-io-module.md), [Answer result](../answer-result.md)

## Contract

- purpose: wake a stopped-but-existing workflow container after an answer file has already been persisted, so older or inotify-unavailable wait scripts can resume from the newly answered gate file.
- owner: exposed as the [docker-start](groom-docker-io-module.md#docker-start) helper on the [Groom Docker I/O module](groom-docker-io-module.md); the focused fallback concept documents the domain meaning of that helper when used by gate answering.
- caller: only the [gate-answering layer](gate-answering-layer.md) uses this fallback in current Groom behavior, and only after the target gate file write has succeeded, stale-answer guards have passed, and process-local gate state has been cleared.
- guard: the [container running-state check](container-running-state-check.md) must report that `container_id` is not currently running; a running container follows the normal in-place wake path and must not invoke Docker start.
- sequencing: the fallback runs while the gate-answering layer still holds the [per-gate answer lock](per-gate-answer-lock.md), after `STATUS: ANSWERED` has been written and after the in-memory gate clear has been requested, so a second same-gate submission cannot interleave between the successful write and the restart decision.
- input: `container_id` is the Docker container id for the selected workflow container; it is passed unchanged to `docker start` and is not resolved from labels, names, compose metadata, or Groom registry state.
- input validation: this helper does not check whether `container_id` is empty, exists, names a Groom-owned container, or is already running; Docker reports those cases through the start command's exit status or subprocess failure.
- command effect: runs exactly one `docker start <container_id>` attempt through the [Docker subprocess runner](docker-subprocess-runner.md) with argv `['docker', 'start', container_id]` and Groom's Docker command timeout.
- timeout: the start attempt uses the shared Docker command timeout of 20 seconds.
- process I/O: the start attempt sends no stdin, captures stdout and stderr as text through the subprocess runner, and discards those streams after reading the exit status.
- output: returns `True` only when Docker runs to completion and exits with status `0`; the helper returns no structured stdout, stderr, or diagnostic message.
- output: returns `False` when Docker runs to completion and exits with any non-zero status, including already-running, missing-container, permission, or daemon-level failures reported as command failures.
- success effect: if the Docker start command exits with status `0`, the gate-answering result remains successful and uses message `answered and restarted`.
- failure effect: if the Docker start command exits non-zero, the gate-answering result still reports `ok=true` because the answer file was already written, but uses message `answer written but restart failed — start the container manually`.
- exception boundary: subprocess launch failures, timeout failures, and unexpected Docker wrapper exceptions are not converted to `False` or to an answer result by this fallback helper; they propagate through the gate-answering call.
- retry behavior: performs no retry, backoff, second running-state check, or post-start inspection; the command exit status is the entire success signal.
- non-effect: does not recreate removed containers, run `docker compose up`, rebuild images, infer compose service names, restore environment variables, reattach volumes, rescan gates, broadcast dashboard HTML, or mutate in-memory workflow state.

## Fields

### field-container-id

- type: `str`
- default: none
- required: true
- meaning: Docker container identifier selected by the gate-answering caller after a successful answer write; passed unchanged as the target of `docker start`.
- constraints: not normalized, ownership-checked, trimmed, or resolved by this fallback; Docker decides whether the id exists, is startable, already running, or invalid.

### field-docker-start-argv

- type: `list[str]`
- default: computed as `["docker", "start", container_id]`
- required: true
- meaning: subprocess argument vector for the single start attempt.
- constraints: always exactly three tokens; the first two tokens are the Docker command and `start` subcommand, and the third token is the unmodified `container_id`.

### field-start-timeout-seconds

- type: `int`
- default: `20`
- required: true
- meaning: maximum runtime for the Docker start process, inherited from the Groom Docker I/O module's shared Docker timeout.
- constraints: this fallback exposes no per-call override and no retry after a timeout exception.

### field-started

- type: `bool`
- default: computed from the completed Docker process return code
- required: true
- meaning: boolean result returned to the gate-answering layer after a completed Docker start attempt.
- constraints: `true` only for return code `0`; every completed non-zero return code is `false`; subprocess launch and timeout exceptions do not produce this field value.

## Methods

### docker-start

- sig: `docker_start(container_id: str) -> bool`
- abstract: false
- raises: Propagates subprocess launch, timeout, and other unexpected subprocess wrapper exceptions.
- returns: `True` for a zero Docker exit status and `False` for a completed non-zero Docker exit status.
- code: groom/groom/docker_io.py::docker_start
- detail: [Groom Docker I/O module docker-start method](groom-docker-io-module.md#docker-start)

Attempts to start one existing Docker container id and returns only whether Docker reported success.

#### Parameters

- container_id: required string; passed as the third argv token to `docker start` without lookup, trimming, normalization, or ownership validation.

#### Effects

- calls: the [Docker subprocess runner](docker-subprocess-runner.md#run) with argv `['docker', 'start', container_id]`, timeout `DOCKER_TIMEOUT`, and no stdin payload.
- interprets: the completed process return code as a boolean success signal.
- ignores: stdout and stderr content for the returned value.
- propagates: subprocess launch and timeout exceptions instead of converting them to `False`.
- does not call: [container running-state check](container-running-state-check.md), workspace-volume readers or writers, workflow-state mutation helpers, or dashboard broadcast helpers.

## Algorithm

- step: Receive a `container_id` that the caller has already decided is stopped.
- step: Invoke the [Docker subprocess runner](docker-subprocess-runner.md) with argv `docker`, `start`, and the exact `container_id`, using the shared Docker command timeout and no stdin.
- step: Return `True` when the command exits with status `0`.
- step: Return `False` when Docker runs but exits with any non-zero status; do not inspect stdout or stderr before making this decision.
- step: Leave subprocess launch and timeout exceptions for the caller to handle; the fallback does not map them to a manual-recovery answer result.

## Caller Outcomes

- outcome: if the gate-answering layer's running-state check reports `true`, this fallback is not called and the answer result message is `answered`.
- outcome: if this fallback returns `true`, the gate-answering layer returns `AnswerResult(ok=True, message="answered and restarted")`.
- outcome: if this fallback returns `false`, the gate-answering layer returns `AnswerResult(ok=True, message="answer written but restart failed — start the container manually")` because the answer file was already written successfully.
- outcome: if the Docker subprocess launch or timeout raises, no fallback boolean is produced; the exception propagates through the gate-answering layer after any already-completed answer-file write and in-memory gate clear.

## Boundaries

- normal path: a running container is expected to have an in-container wait script blocked on the answered file, so the answer write wakes it without any restart attempt.
- caller-owned precondition: the fallback assumes the caller already performed the running-state check; if a caller bypasses that guard, any already-running result is interpreted only through Docker's `docker start` exit status.
- fallback path: a stopped existing container may be an older workflow, an inotify-unavailable wait path, a crashed container, or a manually stopped container; the fallback only tries to start that same container.
- manual recovery: if Docker cannot start that container, the operator-facing message says to start it manually because Groom has no broader recreation path.
