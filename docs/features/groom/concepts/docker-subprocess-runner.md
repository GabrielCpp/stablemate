---
type: concept
slug: docker-subprocess-runner
title: Docker subprocess runner
---
# Docker subprocess runner

Docker subprocess runner is the shared process-execution layer used by Groom's Docker I/O helpers, including the [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume repository-directory reader](workspace-volume-repository-directory-reader.md), [workspace volume file writer](workspace-volume-file-writer.md), [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md), [workspace volume diff reader](workspace-volume-diff-reader.md), [Docker inspection reader](docker-inspection-reader.md), [Docker all-container listing reader](docker-all-container-listing-reader.md), [Docker container-id listing reader](docker-container-id-listing-reader.md), [Docker run-directory reader](docker-run-directory-reader.md), [Docker exec runner](docker-exec-runner.md), [stopped container start fallback](stopped-container-start-fallback.md), and the [host-to-container sidecar query](host-to-container-sidecar-query.md). It accepts one already-tokenized command, starts exactly one local child process without a shell, captures stdout and stderr as text, enforces the caller's timeout, optionally streams text to standard input, and returns the completed process result without interpreting Docker-specific success or failure.

- code: groom/groom/docker_io.py::_run
- refs: [workspace volume file-content reader](workspace-volume-file-content-reader.md), [workspace volume repository-directory reader](workspace-volume-repository-directory-reader.md), [workspace volume file writer](workspace-volume-file-writer.md), [workspace-volume awaiting-file reader](workspace-volume-awaiting-file-reader.md), [workspace volume diff reader](workspace-volume-diff-reader.md), [Docker inspection reader](docker-inspection-reader.md), [Docker all-container listing reader](docker-all-container-listing-reader.md), [Docker container-id listing reader](docker-container-id-listing-reader.md), [Docker run-directory reader](docker-run-directory-reader.md), [Docker exec runner](docker-exec-runner.md), [stopped container start fallback](stopped-container-start-fallback.md), [host-to-container sidecar query](host-to-container-sidecar-query.md)

## Contract

- purpose: provide one consistent execution contract for local Docker CLI commands used by Groom's discovery, file, diff, sidecar, gate-volume, and container-start helpers.
- input argv: `args` is the complete command vector to execute; callers supply each token separately and the runner passes the list through unchanged.
- input timeout: `timeout` is the maximum number of seconds to wait for process completion; it defaults to Groom's shared Docker I/O timeout of 20 seconds.
- input stdin: `input_text` is optional text written to the child process standard input; `None` means no input payload is supplied.
- launch contract: starts the command directly from the argv list with no shell expansion, shell redirection, globbing, command-string parsing, retry, Docker-specific validation, or path normalization.
- process context: uses Groom's current process environment and current working directory; callers cannot override `env`, `cwd`, file descriptors, or stream mode through this runner.
- capture contract: captures both stdout and stderr and decodes both streams as text for the returned process result.
- completion contract: returns a completed process result for every successfully launched command that exits before the timeout, including zero and non-zero exit codes.
- check contract: performs no automatic return-code checking; non-zero exits are represented only by the returned process result's `returncode`.
- nonzero contract: a non-zero return code is data, not an exception; callers decide whether a failed Docker command means empty state, `None`, `False`, fallback, or an endpoint failure.
- failure contract: process launch failures are not converted by this layer and surface to the caller.
- timeout contract: timeout expiration is not converted by this layer and surfaces to the caller.
- state contract: stores no Groom state, emits no dashboard events, mutates no workflow registry, writes no files itself, and creates no domain object; observable effects are only those caused by the invoked child process.

## Fields

### field-command-argv

- type: `list[str]`
- default: none
- required: true
- meaning: complete child-process argument vector, including the executable name as the first token and every flag, value, image, container id, path, or command argument as separate tokens.
- preservation: forwarded as supplied, with no token splitting, shell quoting, wildcard expansion, environment interpolation, path normalization, Docker validation, or retry rewriting by this layer.
- process context: executed in the parent Groom process context with no per-call environment or working-directory override supplied by the runner.
- failure behavior: malformed vectors and missing executables are not converted to Groom-domain errors here; launch failures surface from the subprocess runtime.

### field-timeout-seconds

- type: `int`
- default: `DOCKER_TIMEOUT`, currently `20`
- required: false
- meaning: maximum seconds the child process may run before the subprocess runtime stops waiting and raises its timeout exception.
- preservation: forwarded as supplied; the runner does not clamp, retry, back off, or replace caller-provided timeout values.
- failure behavior: timeout expiration is not represented as a completed process result and is not converted to `None`, `False`, `[]`, or an empty string by this layer.

### field-input-text

- type: `str | None`
- default: `None`
- required: false
- meaning: optional text payload supplied to child-process standard input; `None` means the runner provides no stdin payload.
- preservation: when present, forwarded as text without trimming, appending, encoding by Groom, redacting, line-ending normalization, or status parsing.
- used-by: write helpers such as [workspace volume file writer](workspace-volume-file-writer.md) stream complete replacement file content through this field.

### field-completed-process

- type: `subprocess.CompletedProcess`
- default: none
- required: true
- meaning: return value for any child process that launches and exits before the timeout, carrying the final return code plus captured text stdout and stderr.
- contents: includes the process argv, integer return code, stdout text, and stderr text; Docker-domain callers interpret those fields at their own layer.
- failure behavior: not returned for launch failure or timeout, because those conditions surface as subprocess/runtime exceptions instead.

## Effects

- Starts: exactly one child process from the supplied argv list.
- Supplies: `input_text` to the child process standard input when it is not `None`.
- Captures: child-process standard output and standard error as text.
- Waits: until the child process completes or the caller's timeout expires.
- Returns: the child process args, return code, stdout text, and stderr text as the standard completed-process result.
- Delegates: every Docker-domain interpretation, JSON parsing, path validation, output filtering, fallback decision, and non-zero return-code policy to the caller.
- Preserves: the supplied argv token sequence, timeout value, input text, inherited environment, and inherited working directory without shell parsing, token rewriting, Docker-specific normalization, or per-call process-context overrides.

## Algorithms

### algorithm-run-tokenized-command

- step: Receive the already-tokenized command vector, timeout value, and optional text stdin payload from the caller.
- step: Start one local process directly from the argv vector with stdout capture, stderr capture, text-mode stream handling, the supplied timeout, inherited environment, inherited working directory, and the supplied stdin payload.
- step: If the child process launches and exits before the timeout, return the completed-process result without checking the return code.
- step: If process creation fails, surface the launch exception to the caller.
- step: If the timeout expires before completion, surface the timeout exception to the caller.

## Failure behavior

- Successful process with zero return code: returns the completed-process result unchanged.
- Successful process with non-zero return code: returns the completed-process result unchanged; no Docker-domain exception is raised here.
- Missing executable or launch failure: surfaces the operating-system launch exception to the caller.
- Timeout: surfaces the subprocess timeout exception to the caller.
- Invalid caller-supplied argument shape: not translated into a Groom-domain error by this layer.
- Partial output on failure: any stdout or stderr captured by a completed process is returned with that completed process; output from launch or timeout exceptions is governed by the subprocess runtime exception.

## Boundaries

- Does not decide whether the command is a Docker command; the same contract applies to any argv list supplied by a Groom Docker I/O helper.
- Does not validate Docker volume names, container ids, repository paths, gate file paths, or command payload text.
- Does not parse JSON, split output lines, strip `/vol/` prefixes, sort values, or inspect return codes.
- Does not expose lower-level subprocess options such as `env`, `cwd`, `check`, streaming pipes, custom encoding, or file-descriptor inheritance; the runner's public contract is intentionally fixed to captured text output.
- Does not catch or wrap standard-library subprocess exceptions; the standard-library subprocess runtime is the boundary below this concept.
- Does not emit websocket frames, write HTTP responses, update sidecar sessions, answer gates, mutate Docker volumes, or start workflow containers except through the child process the caller requested.

## Methods

### run

- sig: `_run(args: list[str], timeout: int = DOCKER_TIMEOUT, input_text: str | None = None) -> subprocess.CompletedProcess`
- abstract: false
- raises: process launch exceptions from the operating system and timeout exceptions from the subprocess runtime are intentionally surfaced rather than mapped to Docker-domain return values.
- returns: a text-mode process result containing args, return code, stdout, and stderr when the child process launches and finishes before the timeout.
- code: groom/groom/docker_io.py::_run
- args: [field-command-argv](#field-command-argv); required; no default.
- timeout: [field-timeout-seconds](#field-timeout-seconds); optional; default is `DOCKER_TIMEOUT`, currently 20 seconds.
- input_text: [field-input-text](#field-input-text); optional; default is `None`.
- output: [field-completed-process](#field-completed-process) for successfully launched processes that finish before timeout.

Runs one caller-supplied command vector under the shared Groom subprocess contract and returns the completed child-process result for caller-specific interpretation.

#### Effects

- calls: the standard subprocess runtime exactly once for the supplied argv vector.
- captures: stdout and stderr as text on the returned completed-process value.
- sends: [field-input-text](#field-input-text) as child-process stdin when present.
- returns: [field-completed-process](#field-completed-process) unchanged with no return-code interpretation.
- propagates: launch and timeout exceptions without wrapping them in a Groom-domain result.
- bottoms out: calls only the standard-library subprocess runtime and no deeper first-party Groom symbol.
