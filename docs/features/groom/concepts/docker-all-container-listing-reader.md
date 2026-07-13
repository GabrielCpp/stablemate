---
type: concept
slug: docker-all-container-listing-reader
title: Docker all-container listing reader
---
# Docker all-container listing reader

Docker all-container listing reader is Groom's raw Docker fleet enumerator and a public member of the [Groom Docker I/O module](groom-docker-io-module.md). The [workflow discovery scan](workflow-discovery-scan.md) uses it to ask Docker for every known container, receive one newline-delimited [Docker ps container row](../docker-ps-container-row.md) per reported container through the shared [Docker subprocess runner](docker-subprocess-runner.md), drop blank or malformed rows, and return the remaining parsed row values in Docker's original order for caller-specific filtering.

- code: groom/groom/docker_io.py::docker_ps_all
- refs: [Groom Docker I/O module](groom-docker-io-module.md), [Docker subprocess runner](docker-subprocess-runner.md), [Docker ps container row](../docker-ps-container-row.md), [workflow discovery scan](workflow-discovery-scan.md)

## Contract

- purpose: provide a best-effort raw listing of all Docker containers visible to the Groom process without deciding whether any row is a workhorse workflow container.
- input: no caller-supplied arguments; the local Docker CLI environment and daemon determine which containers are visible.
- command: invokes the Docker CLI as `docker ps -a --format "{{json .}}"` through the shared subprocess runner.
- output: returns a `list[dict[str, Any]]`-intended sequence containing one parsed JSON value for each non-empty stdout line that can be decoded as JSON.
- ordering: preserves Docker stdout line order for every retained row; blank lines and malformed JSON lines are removed without re-sorting the remaining rows.
- parse boundary: trims surrounding whitespace from each stdout line before decoding, skips empty lines, and suppresses JSON decode failures per line.
- validation boundary: does not require the parsed value to be a dictionary and does not require any specific Docker field; callers that need `ID`, mount metadata, state, or labels must validate those fields themselves.
- failure: returns `[]` when the Docker command exits non-zero, treating an unreachable Docker daemon or failed listing as an empty best-effort discovery input.
- failure boundary: process launch failures and subprocess timeout errors from the shared runner are not converted by this layer.
- side effects: performs only the Docker listing read; it does not inspect containers, start or stop containers, read mounted volumes, mutate the workflow registry, broadcast dashboard fragments, answer gates, or persist data.

## Fields

### field-docker-ps-all-command

- type: `list[str]`
- default: `["docker", "ps", "-a", "--format", "{{json .}}"]`
- required: true
- code: groom/groom/docker_io.py::docker_ps_all
- meaning: complete Docker CLI argument vector used to request every known container as one JSON object per stdout line.
- constraints: the command includes stopped containers through `-a`, uses Docker's JSON formatting token unchanged, and is passed as an already-tokenized argv list to the subprocess runner.

### field-completed-stdout-lines

- type: `list[str]`
- default: derived from the completed process `stdout` by splitting on line boundaries.
- required: true
- code: groom/groom/docker_io.py::docker_ps_all
- meaning: raw Docker listing lines scanned after a successful Docker process return code.
- constraints: each line is stripped before validation; empty stripped lines are ignored and do not create output rows.

### field-parsed-container-entries

- type: `list[Any]`
- default: `[]`
- required: true
- code: groom/groom/docker_io.py::docker_ps_all
- meaning: accumulated JSON-decoded row values emitted to callers.
- constraints: successfully decoded values are appended in stdout order; the reader does not enforce dictionary shape even though its type annotation and downstream discovery path expect Docker object rows.

## Effects

- Calls: the shared [Docker subprocess runner](docker-subprocess-runner.md) once with the tokenized `docker ps -a --format "{{json .}}"` command and the default Docker timeout.
- Short-circuits: returns `[]` immediately when the completed Docker process has a non-zero return code.
- Reads: the completed process stdout as newline-delimited Docker container rows.
- Filters: ignores lines that become empty after trimming whitespace.
- Parses: decodes each remaining line as JSON and appends successfully decoded values to the result list.
- Suppresses: ignores `json.JSONDecodeError` for an individual row so one malformed line does not discard previously parsed rows or prevent later rows from being considered.
- Emits: the accumulated parsed row list unchanged after the stdout scan completes.

## Failure behavior

- Docker command non-zero: returns `[]`, allowing discovery callers to treat an unavailable all-container listing as no listing rows from this helper.
- Blank stdout line: ignores the line and continues scanning later lines.
- Malformed JSON line: ignores only that line and continues scanning later lines.
- Valid non-object JSON line: includes the decoded value in the returned list; callers own field and shape validation.
- Process launch failure: propagates the subprocess/runtime exception from the [Docker subprocess runner](docker-subprocess-runner.md).
- Timeout: propagates the subprocess timeout exception from the [Docker subprocess runner](docker-subprocess-runner.md).

## Boundaries

- Does not distinguish an empty Docker fleet from a non-zero `docker ps` result; both are represented as an empty returned list at this layer.
- Does not truncate or normalize container ids; the [workflow discovery scan](workflow-discovery-scan.md) reads the `ID` field it needs from returned rows.
- Does not inspect containers, validate workhorse mount contracts, query sidecars, read volumes, or infer [workflow container](workflow-container.md) records.
- Does not log skipped malformed rows, expose stderr, retry the Docker command, or persist the listing output.

## Algorithms

### algorithm-read-all-container-rows

- step: Invoke the shared Docker subprocess runner with the all-container JSON-line command vector.
- step: If the completed process return code is non-zero, return an empty list without reading stdout.
- step: Initialize an empty result list for parsed row values.
- step: Split stdout into lines, preserving the line order reported by Docker.
- step: Strip surrounding whitespace from each line.
- step: Skip the line when the stripped value is empty.
- step: Decode the stripped line as JSON.
- step: Append the decoded value to the result list when JSON decoding succeeds.
- step: Ignore only the current line when JSON decoding fails, then continue scanning later lines.
- step: Return the accumulated result list unchanged.

## Methods

### docker-ps-all

- sig: `docker_ps_all() -> list[dict[str, Any]]`
- abstract: false
- raises: subprocess launch and timeout exceptions from the shared runner are intentionally surfaced rather than mapped to an empty listing.
- returns: parseable rows from Docker's all-container JSON-line listing, or an empty list when Docker reports the listing command failed.
- args: none.

Returns every parseable Docker all-container row visible to the Groom process without interpreting the rows as workflows. Callers receive the retained decoded values in Docker output order and must decide which fields are required for their own use.

#### Effects

- calls: [Docker subprocess runner](docker-subprocess-runner.md) with [field-docker-ps-all-command](#field-docker-ps-all-command).
- reads: [field-completed-stdout-lines](#field-completed-stdout-lines) only when Docker exits successfully.
- emits: [field-parsed-container-entries](#field-parsed-container-entries) after blank-line filtering and per-line JSON decoding.
- propagates: subprocess launch and timeout exceptions from the runner.
- bottoms out: calls no deeper first-party Groom symbol beyond the documented subprocess runner.
