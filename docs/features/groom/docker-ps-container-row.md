---
type: format
slug: docker-ps-container-row
title: Docker ps container row
---
# Docker ps container row

Docker ps container row is one JSON-line value emitted by Docker's `docker ps -a --format "{{json .}}"` command and accepted by Groom's [Docker all-container listing reader](concepts/docker-all-container-listing-reader.md). The reader preserves each successfully decoded JSON value without validating it as an object. The [workflow discovery scan](concepts/workflow-discovery-scan.md) considers only decoded object rows with a truthy `ID` value as candidate containers; it ignores every other Docker-provided field.

- file: not an on-disk Groom artifact; this is one stdout line from the Docker CLI `docker ps -a --format "{{json .}}"` stream.
- code: `groom/groom/docker_io.py::docker_ps_all`
- detail: [Docker all-container listing reader](concepts/docker-all-container-listing-reader.md)
- tests: `groom/tests/test_discovery.py::test_scan_skips_containers_that_are_not_workhorse_containers`

## Contract

- producer: Docker CLI emits one JSON value per container row when invoked with `docker ps -a --format "{{json .}}"`.
- consumer: Groom's all-container listing reader parses each line independently and returns decoded values to discovery; discovery keeps decoded object rows with a truthy `ID` field and ignores rows without one.
- framing: each row occupies one stdout line; blank lines are ignored before JSON parsing.
- malformed row handling: a line that is not valid JSON is skipped by the listing reader and is not represented in the returned row list.
- extra fields: Docker may include fields outside this contract; Groom passes them through from the listing reader and current discovery logic ignores them.
- validation boundary: this format describes the intended Docker object shape, but the listing reader itself does not reject decoded non-object JSON values.

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
