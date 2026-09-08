---
type: concept
slug: docker-all-container-listing-reader
title: Docker all-container listing reader
---
# Docker all-container listing reader

Docker all-container listing reader is the raw Docker fleet enumerator exposed by the [Groom Docker I/O module](groom-docker-io-module.md). The [workflow discovery scan](workflow-discovery-scan.md) uses it to obtain every Docker container row before inspecting and classifying candidates. It returns parsed rows only; workhorse eligibility and workflow-state interpretation belong to discovery, while process execution belongs to the [Docker subprocess runner](docker-subprocess-runner.md).

- code: `groom/groom/docker_io.py::docker_ps_all`
- detail: [Docker ps-all documentation scope](docker-ps-all-documentation-scope.md)

The reader invokes `docker ps -a --format "{{json .}}"` as a tokenized command with the shared twenty-second timeout. A successful command is read as newline-delimited JSON: surrounding whitespace is removed, blank lines are ignored, valid JSON values are retained in Docker's original order, and a malformed line is skipped without affecting other lines. A non-zero command result produces an empty list. Launch and timeout exceptions from the subprocess runner remain exceptions at this boundary.

## Contract

The function accepts no caller arguments and uses the local Docker CLI and daemon as its only input. Its public annotation is `list[dict[str, Any]]`; the implementation does not validate that decoded JSON values are dictionaries or that they contain an `ID` field. Consumers therefore own row-shape and field validation. The reader has no state, persistence, logging, retry, container mutation, volume access, or workflow classification side effect.

## Fields

### field: docker-ps-all-command

- type: `list[str]`
- default: `['docker', 'ps', '-a', '--format', '{{json .}}']`
- required: true
- code: `groom/groom/docker_io.py::docker_ps_all`
- detail: [Docker ps all field guide](docker-ps-all-field-guide.md)
- detail: [Docker ps-all value pipeline](docker-ps-all-value-pipeline.md)

The complete argv vector requests all containers, including stopped containers, and asks Docker to emit one JSON object per output line. The vector is passed to the subprocess runner without shell parsing or token rewriting.

### field: completed-stdout-lines

- type: `list[str]`
- default: derived from completed-process stdout
- required: true
- code: `groom/groom/docker_io.py::docker_ps_all`
- detail: [Docker ps all field guide](docker-ps-all-field-guide.md)
- detail: [Docker ps-all value pipeline](docker-ps-all-value-pipeline.md)

These are the stdout lines produced by a zero-exit Docker command, split at line boundaries. Each line is stripped before the reader decides whether it is empty or parseable.

### field: parsed-container-entries

- type: `list[Any]`
- default: `[]`
- required: true
- code: `groom/groom/docker_io.py::docker_ps_all`
- detail: [Docker ps all field guide](docker-ps-all-field-guide.md)
- detail: [Docker ps-all value pipeline](docker-ps-all-value-pipeline.md)

This is the result sequence accumulated from successfully decoded lines. It preserves retained values and their input order, including a decoded non-object value if Docker supplies one.

## Methods

### method: docker-ps-all

- sig: `docker_ps_all() -> list[dict[str, Any]]`
- abstract: false
- raises: subprocess launch and timeout exceptions from the [Docker subprocess runner](docker-subprocess-runner.md) propagate.
- returns: empty list when Docker exits non-zero
- verify: count(subject="result", equals=0)
- returns: parsed JSON values from Docker's all-container listing in stdout order
- code: `groom/groom/docker_io.py::docker_ps_all`
- detail: [Docker ps-all documentation scope](docker-ps-all-documentation-scope.md)

The method performs one best-effort read and does not decide whether any returned row represents a workflow container. It does not inspect container metadata, normalize ids, sort rows, expose stderr, retry failures, or persist the listing.

#### Algorithm

The reader invokes the subprocess runner with `docker ps -a --format "{{json .}}"` and the default Docker timeout. A completed process with a non-zero return code yields `[]`. For successful output, the reader splits stdout into lines in their original order, strips each line, and skips empty lines. It decodes each remaining line as JSON, appends successfully decoded values to the result sequence, and ignores only the current line when decoding raises `JSONDecodeError`. After all lines are processed, it returns the accumulated sequence.

The standard-library JSON parser and subprocess runtime are below this bounded Groom concept. The discovery consumer reads the returned `ID` fields and performs the next layer of inspection.
