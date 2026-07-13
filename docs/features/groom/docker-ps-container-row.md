---
type: format
slug: docker-ps-container-row
title: Docker ps container row
---
# Docker ps container row

Docker ps container row is one JSON-line object emitted by Docker's `docker ps -a --format "{{json .}}"` command and accepted by Groom's [Docker all-container listing reader](concepts/docker-all-container-listing-reader.md). The [workflow discovery scan](concepts/workflow-discovery-scan.md) consumes only the row's `ID` value to select candidate containers; every other Docker-provided field is treated as optional pass-through metadata and ignored by that scan layer.

- file: not an on-disk Groom artifact; this is one stdout line from the Docker CLI `docker ps -a --format "{{json .}}"` stream.

## Contract

- producer: Docker CLI emits one JSON object per container row when invoked with `docker ps -a --format "{{json .}}"`.
- consumer: Groom's all-container listing reader parses each line independently and returns decoded rows to discovery; discovery keeps rows with a truthy `ID` field and ignores rows without one.
- framing: each row occupies one stdout line; blank lines are ignored before JSON parsing.
- malformed row handling: a line that is not valid JSON is skipped by the listing reader and is not represented in the returned row list.
- extra fields: Docker may include fields outside this contract; Groom passes them through from the listing reader and current discovery logic ignores them.
- validation boundary: this format describes the intended Docker object shape, but the listing reader itself does not reject decoded non-object JSON values.

## Fields

### field-id

- type: `str`
- default: missing
- required: false
- meaning: Docker's reported container id for this row; the workflow discovery scan treats a truthy value as a candidate id and drops rows where the field is absent or falsey.

### field-extra-docker-fields

- type: `Any`
- default: omitted
- required: false
- meaning: any additional keys Docker includes for the row, such as image, command, status, names, labels, ports, or size metadata; Groom's documented discovery scan does not interpret these fields.
