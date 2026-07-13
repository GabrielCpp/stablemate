---
type: concept
slug: docker-container-id-listing-reader
title: Docker container-id listing reader
---
# Docker container-id listing reader

Docker container-id listing reader is Groom's current-container existence lookup for the [workflow discovery scan](workflow-discovery-scan.md#method-present-container-ids) and a public helper indexed by the [Groom Docker I/O module](groom-docker-io-module.md#list-container-ids). It asks Docker for every currently known container id through the shared [Docker subprocess runner](docker-subprocess-runner.md), normalizes each non-empty stdout line to Docker's twelve-character short id form, and preserves the distinction between a reachable empty Docker fleet and an unreachable or failed Docker listing command.

- code: groom/groom/docker_io.py::list_container_ids
- verify: groom/tests/test_docker_io.py::test_list_container_ids_returns_short_id_set
- verify: groom/tests/test_docker_io.py::test_list_container_ids_returns_none_on_docker_failure
- verify: groom/tests/test_docker_io.py::test_list_container_ids_empty_when_no_containers
- refs: [Groom Docker I/O module](groom-docker-io-module.md#list-container-ids), [Docker subprocess runner](docker-subprocess-runner.md)

## Contract

- purpose: report the set of Docker container ids that currently exist so stale workflow-registry entries can be pruned only when Docker was reachable.
- input: no caller-supplied arguments; the local Docker CLI environment and daemon determine which containers are visible.
- command: invokes the Docker CLI as `docker ps -aq` through the shared subprocess runner.
- output: returns `set[str]` when the Docker command exits successfully; each member is a non-empty stdout line stripped of surrounding whitespace and truncated to at most twelve characters.
- output: returns an empty set when Docker exits successfully but reports no container ids.
- output: returns `None` when the Docker command exits non-zero, allowing callers to distinguish a failed Docker lookup from a successful empty fleet.
- normalization: stores ids in a set, so duplicate lines collapse to one normalized id and result ordering is not part of the contract.
- validation boundary: does not inspect containers, verify that an id belongs to a workhorse workflow container, or validate Docker's id characters beyond ignoring blank lines.
- failure boundary: process launch failures and subprocess timeout errors from the shared runner are not converted to `None` by this layer.
- side effects: performs only the Docker listing read; it does not mutate the workflow registry, start or stop containers, read mounted volumes, broadcast dashboard fragments, answer gates, or persist data.

## Effects

- Calls: the shared [Docker subprocess runner](docker-subprocess-runner.md) once with the tokenized `docker ps -aq` command and the default Docker timeout.
- Short-circuits: returns `None` immediately when the completed Docker process has a non-zero return code.
- Reads: the completed process stdout as newline-delimited Docker container ids.
- Filters: ignores lines that become empty after trimming whitespace.
- Normalizes: truncates each retained line to its first twelve characters, matching Docker's short-id display form used by the workflow registry.
- Emits: a set containing every normalized id when the Docker listing succeeds, including the empty set for a successful listing with no retained lines.

## Algorithms

### algorithm-list-current-container-ids

- step: Invoke the shared Docker subprocess runner with `docker ps -aq` and the default Docker timeout.
- step: If the completed process has a non-zero return code, return `None` without interpreting stdout.
- step: Split stdout into lines.
- step: Strip surrounding whitespace from each line.
- step: Drop every stripped line that is empty.
- step: Truncate each retained line to its first twelve characters.
- step: Return the retained short ids as a set, collapsing duplicates and exposing no ordering contract.

## Failure behavior

- Docker command failure: returns `None` for any completed Docker process whose return code is non-zero.
- Empty Docker fleet: returns `set()` when Docker exits successfully and stdout contains no retained id lines.
- Blank stdout lines: ignored without making the listing fail.
- Duplicate ids: collapse to one set member after twelve-character normalization.
- Long ids: truncated to twelve characters before insertion into the output set.
- Short ids: retained unchanged when shorter than twelve characters.
- Process launch failure: propagates the shared runner's launch exception.
- Timeout: propagates the shared runner's timeout exception.
- Stderr: ignored by this reader; the return code alone decides the `None` branch.

## Boundaries

- Does not inspect containers, read Docker labels, read Docker mounts, query sidecars, or decide whether a container is workhorse-backed.
- Does not sort ids or preserve Docker's listing order.
- Does not validate hexadecimal shape, id length, container state, image, name, labels, or registry membership.
- Does not mutate Docker containers, workflow registry records, sidecar sessions, mounted volumes, dashboard clients, gate files, or answer files.
- Does not catch standard-library subprocess launch or timeout exceptions; the [Docker subprocess runner](docker-subprocess-runner.md) is the boundary below this helper.

## Methods

### list-container-ids

- sig: `list_container_ids() -> set[str] | None`
- abstract: false
- raises: subprocess launch and timeout exceptions from the shared runner are intentionally surfaced rather than mapped to `None`.
- returns: a set of twelve-character-or-shorter container id strings when Docker exits successfully, or `None` when Docker exits non-zero.
- code: groom/groom/docker_io.py::list_container_ids
- verify: groom/tests/test_docker_io.py::test_list_container_ids_returns_short_id_set
- verify: groom/tests/test_docker_io.py::test_list_container_ids_returns_none_on_docker_failure
- verify: groom/tests/test_docker_io.py::test_list_container_ids_empty_when_no_containers

Returns the normalized short-id set for every Docker container currently known to Docker. The method is intentionally an existence reader for prune safety: a successful empty set means Docker was reachable and no containers are present, while `None` means Docker could not provide a reliable listing and callers must not infer absence.

#### Contract

- input: no caller-supplied arguments.
- command: calls the shared Docker subprocess runner with `docker ps -aq` and the default Docker timeout.
- success output: `set[str]` containing every non-empty stdout line stripped and truncated to twelve characters.
- empty success output: `set()` when the Docker command succeeds and stdout has no retained id lines.
- failure output: `None` when the Docker command completes with a non-zero return code.
- ordering: no ordering is exposed because the output is a set.
- id scope: includes every Docker container id reported by Docker, not only workhorse-backed containers and not only containers present in Groom's registry.
- side effects: performs one Docker listing read and no Groom state mutation.

#### Effects

- Calls: [Docker subprocess runner](docker-subprocess-runner.md) once.
- Reads: completed process return code and stdout.
- Filters: blank stdout lines after whitespace stripping.
- Normalizes: each retained id to its first twelve characters.
- Returns: either the normalized id set or the negative-capability `None` signal.
