---
type: format
slug: docker-ps-container-row
title: Docker ps container row
---
# Docker ps container row

Docker ps container row is one JSON-line value emitted by Docker's `docker ps -a --format "{{json .}}"` command and accepted by Groom's [Docker all-container listing reader](concepts/docker-all-container-listing-reader.md). This format describes the intended Docker object shape, but [`docker_ps_all`](../../../groom/groom/docker_io.py) preserves each successfully decoded JSON value without validating it as an object — it does not reject a decoded non-object JSON value — and [`scan`](../../../groom/groom/discovery.py) calls `entry.get("ID", "")` to derive the container IDs it inspects. Docker's normal output therefore needs to decode to object rows for discovery to proceed; fields other than `ID` are not used by the scan.

- file: not an on-disk Groom artifact; this is one stdout line from the Docker CLI `docker ps -a --format "{{json .}}"` stream.
- code: `groom/groom/docker_io.py::docker_ps_all`
- detail: [Docker all-container listing reader](concepts/docker-all-container-listing-reader.md)
- tests: `groom/tests/test_discovery.py::test_scan_skips_containers_that_are_not_workhorse_containers`

## Contract

- producer: Docker CLI emits one JSON value per container row when invoked with `docker ps -a --format "{{json .}}"`.
- framing: each row occupies one stdout line; blank lines are ignored before JSON parsing.
- malformed row handling: a line that is not valid JSON is skipped by the listing reader and is not represented in the returned row list.
- extra fields: Docker may include fields outside this contract; Groom passes them through from the listing reader and current discovery logic ignores them.

## Fields

### ID

- type: `str`
- default: absent
- required: false
- semantics: Docker's reported container id is the only row field the workflow discovery scan uses to select a candidate for inspection.
- verify: json_path(path="$.ID", matches=".+")
- code: `groom/groom/discovery.py::scan`

### additional Docker fields

- type: `Any`
- default: omitted
- required: false
- semantics: image, command, status, names, labels, ports, size metadata, and other Docker-provided fields pass through the listing reader but do not affect workflow discovery.
- code: `groom/groom/docker_io.py::docker_ps_all`
- detail: [Docker ps-all value pipeline](concepts/docker-ps-all-value-pipeline.md)
