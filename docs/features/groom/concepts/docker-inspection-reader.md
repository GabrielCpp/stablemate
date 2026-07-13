---
type: concept
slug: docker-inspection-reader
title: Docker inspection reader
---
# Docker inspection reader

Docker inspection reader is the [Groom Docker I/O module](groom-docker-io-module.md) member that performs Groom's raw metadata lookup for one Docker container id. The [push-first volume metadata resolver](push-first-volume-metadata-resolver.md), [workflow discovery scan](workflow-discovery-scan.md), and [container running-state check](container-running-state-check.md) use it to request one [Docker inspect container object](../docker-inspect-container-object.md) through the shared [Docker subprocess runner](docker-subprocess-runner.md), treating Docker command failures, malformed JSON, and empty inspect arrays as absent metadata while leaving every workhorse-specific classification and mutation decision to consumers.

- code: groom/groom/docker_io.py::docker_inspect
- refs: [Groom Docker I/O module](groom-docker-io-module.md), [Docker subprocess runner](docker-subprocess-runner.md), [Docker inspect container object](../docker-inspect-container-object.md), [push-first volume metadata resolver](push-first-volume-metadata-resolver.md), [workflow discovery scan](workflow-discovery-scan.md), [container running-state check](container-running-state-check.md)

## Contract

- purpose: fetch Docker daemon metadata for one known or suspected workflow container without interpreting workhorse-specific mounts, environment values, lifecycle state, or dashboard behavior.
- input: `container_id` is a required string passed as the sole container selector to `docker inspect`; this layer does not normalize, truncate, validate, or quote it beyond passing it as one argv token.
- input boundary: accepts full ids, short ids, names, or any other selector string Docker itself accepts; an invalid selector is represented only by Docker's process result.
- command: invokes the Docker CLI as `docker inspect <container_id>` through the shared subprocess runner.
- argv contract: constructs exactly three argv tokens, `docker`, `inspect`, and the supplied id; no shell expansion, concatenated command string, stdin payload, or caller-provided Docker flag is used.
- timeout: inherits the Docker subprocess runner's default twenty-second timeout; callers do not pass a per-call timeout to this reader.
- blocking boundary: this reader is synchronous and owns no event-loop handoff; asynchronous callers that need non-blocking behavior must run it outside the event loop before interpreting the result.
- stdout contract: reads standard output only when the Docker process return code is zero; stderr is never parsed or surfaced as a Groom-domain value.
- success output: returns the first item from the parsed Docker JSON value when the command exits successfully and the parsed value is truthy.
- return type boundary: the public type contract is `dict[str, Any] | None`, but the reader itself does not runtime-check that the first truthy decoded item is a mapping; consumers own the accepted inspect-object shape.
- absent output: returns `None` when the Docker CLI exits non-zero, stdout is not valid JSON, or the parsed JSON value is falsey, including Docker's expected empty inspect array.
- shape boundary: treats the parsed JSON value only as an indexable sequence; it does not require the top-level value to be a list or require the first item to be a mapping before returning it.
- validation boundary: does not verify that the returned object describes a workhorse container, does not require workflow mounts, does not parse environment variables, and does not inspect lifecycle fields itself.
- failure boundary: process launch errors, subprocess timeout errors, and truthy valid-JSON shape errors outside first-item access are not converted to `None` by this layer.
- side effects: performs only the Docker metadata read; it does not mutate the workflow registry, start containers, read mounted volumes, broadcast dashboard fragments, or persist data.
- consumer contract: callers must distinguish `None` from an accepted [Docker inspect container object](../docker-inspect-container-object.md) and decide their own fallback, mutation, or boolean result.
- direct callers: the [workflow discovery scan](workflow-discovery-scan.md#method-resolve-container) calls this reader once per Docker ps id before classifying workflow containers; the [push-first volume metadata resolver](push-first-volume-metadata-resolver.md#method-ensure-volumes) calls it when a push-first registry entry lacks Docker volume metadata; the [container running-state check](container-running-state-check.md#is-running) calls it when deciding whether a successfully answered gate needs the stopped-container start fallback.

## Effects

- Calls: the [Docker subprocess runner](docker-subprocess-runner.md) with argv `docker inspect <container_id>` and no stdin.
- Reads: Docker daemon metadata visible to the host-side Groom process for the supplied id.
- Checks: only the Docker process return code before deciding whether stdout is parseable metadata.
- Parses: standard output as JSON only when the Docker command exits with status `0`.
- Returns: the first parsed element when the parsed value is truthy.
- Returns: `None` for Docker command failure, malformed JSON stdout, or a falsey parsed value.
- Preserves: the supplied id string exactly as the Docker selector token.
- Does not: log stderr, inspect stderr text, retry, cache, normalize ids, classify containers, convert metadata into workflow state, or mutate any Groom state.

## Consumers

- workflow discovery: [Workflow discovery scan](workflow-discovery-scan.md#method-resolve-container) treats a `None` result as no resolvable workflow container for that id, then requires the returned object to satisfy the workhorse-container classifier before it builds workflow state.
- workflow discovery: once the returned object is accepted, discovery reuses the same inspect object for container conversion, running-state selection of the sidecar-query path, and volume-fallback selection; it does not call this reader again for that id inside the same resolution.
- push-first volume hydration: [Push-first volume metadata resolver](push-first-volume-metadata-resolver.md#method-ensure-volumes) calls this reader on a worker thread only when the registry entry is absent or lacks `workspace_volume`; a `None` result leaves registry metadata unchanged, while a present object is converted without first requiring the workhorse mount classifier.
- gate answering: [Container running-state check](container-running-state-check.md#is-running) treats `None` as stopped or unavailable and reads only `State.Running` when metadata is present.
- caller boundary: consumers, not this reader, decide whether a missing inspect object means a non-workhorse container, a stopped container, an unreachable Docker daemon, invalid output, or a fallback path.
- verification: no direct unit test exercises `docker_inspect` return parsing; existing discovery and gate tests patch this reader and verify the downstream decisions made from its returned object or `None`.

## Methods

### docker-inspect

- sig: `docker_inspect(container_id: str) -> dict[str, Any] | None`
- abstract: false
- raises: subprocess launch and timeout exceptions from the shared runner; indexing exceptions if a truthy valid JSON value is not compatible with first-item access.
- returns: the first decoded Docker inspect element for a zero-exit, valid-JSON, truthy response; otherwise `None` for non-zero Docker exit, invalid JSON, or falsey decoded JSON.
- code: groom/groom/docker_io.py::docker_inspect
- args: `container_id`; required string; passed unchanged as the only Docker inspect selector token.

The method is the only public Docker-inspection reader in Groom's Docker I/O layer; downstream readers and resolvers own every interpretation of the returned object.

#### Effects

- Calls: [Docker subprocess runner](docker-subprocess-runner.md) with `['docker', 'inspect', container_id]`.
- Supplies: no stdin payload and no explicit timeout override, so the shared Docker timeout applies.
- Returns: `None` without parsing when the Docker process exits non-zero.
- Returns: `None` when successful stdout cannot be decoded as JSON.
- Returns: `None` when decoded JSON is falsey.
- Returns: the decoded first item for any truthy decoded JSON value.
- Does not: inspect stderr, coerce the first item to a mapping, or classify the returned object as a workflow container.

## Algorithms

### algorithm-read-one-container-inspection

- step: Receive a caller-supplied Docker container id string.
- step: Invoke the Docker subprocess runner with `docker inspect` and the id as separate argv tokens.
- step: If the Docker command exits with a non-zero status, return `None` without reading or classifying stderr.
- step: Decode stdout as JSON.
- step: If stdout is not valid JSON, return `None`.
- step: If the decoded JSON value is falsey, return `None`.
- step: Return the first decoded item exactly as decoded and leave all container eligibility, mount, environment, mapping-shape, and running-state interpretation to the caller.

## Failure Semantics

- docker-command-failure: a non-zero Docker exit status is represented as `None`, including missing containers, inaccessible Docker daemon responses that still produce a process result, and Docker CLI validation errors.
- invalid-json: stdout that cannot be parsed as JSON is represented as `None` even when the Docker command exits successfully.
- empty-inspect-output: an empty parsed value is represented as `None`.
- falsey-json-output: any falsey parsed JSON value, not only an empty array, is represented as `None`.
- launch-or-timeout-exception: subprocess launch failures and timeout exceptions propagate from the subprocess runner because this reader only catches JSON decoding failures.
- valid-json-shape-error: a truthy parsed JSON value that cannot supply item `0` may raise the ordinary indexing error for that value; consumers do not receive `None` for that case.
- non-mapping-first-item: a first decoded item that is not a dictionary can be returned to the caller; downstream concepts define which inspect object shapes they accept.
