---
type: concept
slug: docker-exec-runner
title: Docker exec runner
---
# Docker exec runner

Docker exec runner is Groom's host-to-container command helper for executing one already-running [workflow container](workflow-container.md) command through Docker's `exec` operation. The [host-to-container sidecar query](host-to-container-sidecar-query.md) uses it to run `groom-sidecar --query` in-place, and the helper delegates the completed argv to the [Docker subprocess runner](docker-subprocess-runner.md) for shell-free execution, text capture, and timeout enforcement.

- code: groom/groom/docker_io.py::docker_exec
- refs: [host-to-container sidecar query](host-to-container-sidecar-query.md), [Docker subprocess runner](docker-subprocess-runner.md), [workflow container](workflow-container.md)
- verify: groom/tests/test_docker_io.py::test_docker_exec_builds_user_and_env_flags

## Contract

- purpose: build and execute a single `docker exec` command against an existing running container without creating, starting, stopping, or inspecting containers.
- input container id: required container identifier text; appended exactly once as the Docker exec target after all optional Docker exec flags.
- input command args: required ordered command-token list; appended after the container id without host-shell parsing, host quoting interpretation, or token rewriting by Groom.
- input user: optional user override text; when present, emitted as `-u <user>` before the container id; when absent, no Docker user option is emitted and Docker/container defaults apply.
- input environment: optional mapping of environment variable names to string values; each mapping item emits one `-e KEY=VALUE` flag before the container id.
- input environment default: `None` and an empty mapping are equivalent and emit no environment flags.
- input environment order: environment flags preserve the mapping iteration order supplied by the caller.
- input timeout: integer seconds; defaults to Groom's shared Docker I/O timeout of 20 seconds and is forwarded unchanged to the [Docker subprocess runner](docker-subprocess-runner.md).
- output: returns the completed process result from the [Docker subprocess runner](docker-subprocess-runner.md), including argv, return code, stdout text, and stderr text.
- nonzero exit policy: does not convert non-zero Docker exits to `None`, booleans, or exceptions; callers interpret the returned process result according to their own fallback contract.
- exception policy: does not catch process launch failures or timeout exceptions from the subprocess runner; callers that need fallback behavior catch them at the call site.
- security: never invokes a shell and never concatenates the command into a shell string; shell expansion, command injection through token text, and host-side redirection are outside this helper's behavior.
- state: does not mutate Groom's workflow registry, gate files, sidecar session table, dashboard clients, or Docker volumes; observable container effects are limited to whatever short-lived process Docker starts inside the target container.

## Effects

- Builds: starts with argv `docker exec`.
- Adds: `-u <user>` only when the caller supplies a user override.
- Adds: one `-e KEY=VALUE` pair for each supplied environment mapping entry.
- Adds: the target container id after all Docker exec options.
- Adds: the in-container command tokens after the container id in their caller-provided order.
- Calls: the [Docker subprocess runner](docker-subprocess-runner.md) once with the completed argv and the supplied timeout.
- Returns: the subprocess runner's completed process result unchanged.
- Preserves: stdout, stderr, return code, args, and subprocess metadata are not interpreted or rewritten by this helper.

## Algorithm

- step: Initialize an argv list with `docker exec`.
- step: If `user` is present, append the Docker exec user flag and the requested user value.
- step: For every supplied environment mapping entry, append the Docker exec environment flag and its `KEY=VALUE` payload.
- step: Append the container id and every command argument token.
- step: Invoke the Docker subprocess runner with the completed argv and timeout.
- step: Return the completed process result exactly as supplied by the subprocess runner.

## Failure behavior

- Docker non-zero exit: represented only by the returned process result's return code and stderr/stdout streams.
- Missing Docker binary: surfaces as the subprocess runner's launch exception unless the caller catches it.
- Timeout: surfaces as the subprocess runner's timeout exception unless the caller catches it.
- Invalid container id: represented by Docker's returned non-zero process result when Docker starts and rejects the request.
- Invalid command args: represented by Docker's returned non-zero process result when Docker starts and rejects or cannot run the in-container command.

## Methods

### docker_exec

- sig: `docker_exec(container_id: str, args: list[str], *, user: str | None = None, env: dict[str, str] | None = None, timeout: int = DOCKER_TIMEOUT) -> subprocess.CompletedProcess`
- abstract: false
- raises: process launch failures and timeout exceptions surfaced by the [Docker subprocess runner](docker-subprocess-runner.md); Docker non-zero exits are returned as completed process results instead of raised here.
- returns: text-mode completed process result for the single `docker exec` command, preserving args, return code, stdout, and stderr.
- code: groom/groom/docker_io.py::docker_exec
- verify: groom/tests/test_docker_io.py::test_docker_exec_builds_user_and_env_flags
- arg: `container_id`; type `str`; required; no default; identifies the already-running container targeted by Docker exec.
- arg: `args`; type `list[str]`; required; no default; supplies the in-container command argv appended after the container id.
- kwarg: `user`; type `str | None`; optional; default `None`; emits the Docker exec user flag only when present.
- kwarg: `env`; type `dict[str, str] | None`; optional; default `None`; emits one Docker exec environment flag per mapping item when present.
- kwarg: `timeout`; type `int`; optional; default `DOCKER_TIMEOUT`, currently 20 seconds; forwarded unchanged to the subprocess runner.

Builds the host-side Docker exec argv for one already-running container and hands that argv to the shared subprocess layer exactly once. It is intentionally a command-construction boundary: it does not parse Docker output, validate sidecar payloads, retry failed execs, start stopped containers, or map Docker return codes into Groom domain values.
