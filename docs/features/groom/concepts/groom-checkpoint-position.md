---
type: concept
slug: groom-checkpoint-position
title: Groom checkpoint position
---
# Groom checkpoint position

Groom checkpoint position is the normalized representation of a workflow's
current checkpoint state, extracted from the [checkpoint data](../sidecar-run-checkpoint-data.md)
written by workhorse. It bridges two checkpoint formats — the current `pyflow`
engine format and a retired format — into a unified `CheckpointPosition` type,
so consumers like the [sidecar snapshot](sidecar-snapshot.md), 
[workflow discovery scan](workflow-discovery-scan.md), and the dashboard can
read checkpoint state without handling format variations. The transformer tolerates
malformed or incomplete checkpoint JSON and returns safe empty defaults rather
than raising.

- code: groom/groom/checkpoints.py
- tests: groom/tests/test_checkpoints.py

## Contract

- purpose: tolerant deserialization of checkpoint JSON from both active (pyflow)
  and retired engine formats into a normalized `CheckpointPosition` type.
- input: raw checkpoint JSON text read from `/runs/<run-dir>/checkpoint.json` by
  callers like the sidecar snapshot reader, discovery volume fallback, and
  dashboard progress-frame handler.
- output: a `CheckpointPosition` object with a `current_node` string (the graph
  node id) and an optional `waiting_on` string (the gate context file path for
  pyflow format only).
- normalization rule: present values are returned unchanged; missing fields,
  read/parse errors, type mismatches, and non-object JSON collapse to empty
  strings (`""`) rather than raising.
- format support: `pyflow` engine format stores position in `state` field and gate
  context path in `waiting_on` field; retired format stores position in
  `current_id` field only and has no gate-context concept. Both are recognized
  by the exact format-discriminator value of `engine` field.
- format discrimination: when `engine == "pyflow"`, read `state` and `waiting_on`;
  otherwise (including missing/absent engine field) treat the payload as retired
  format and read `current_id` only.

## CheckpointPosition Type

The `CheckpointPosition` dataclass is the normalized output type for parsing
checkpoint JSON. It is a frozen, slotted dataclass with two fields:

- code: groom/groom/checkpoints.py::CheckpointPosition
- tests: groom/tests/test_checkpoints.py

### field: current_node

- type: `str`
- default: `""`
- required: true
- semantics: workhorse graph-node id from the current checkpoint, representing
  the latest node reached or being executed in the workflow run. Empty when the
  checkpoint cannot be read, parsed, or contains no usable position value. Callers
  treat empty values as unknown position.
- code: groom/groom/checkpoints.py::CheckpointPosition.current_node

### field: waiting_on

- type: `str`
- default: `""`
- required: true
- semantics: workspace-relative path to an operator gate context file when the
  workflow is waiting for operator input in pyflow format.
- semantics: empty string when the checkpoint is retired format, contains no gate
  in progress, or the field is missing.
- code: groom/groom/checkpoints.py::CheckpointPosition.waiting_on

## Methods

### parse_position

- sig: `parse_position(text: str) -> CheckpointPosition`
- abstract: false
- does: read JSON text and extract checkpoint position into a normalized type
- does: absorb malformed JSON, type errors, and missing fields without raising
- raises: none — all error cases (parse failures, type mismatches, missing keys)
  return an empty `CheckpointPosition()` instead of raising
- verify: json_path(path="$.current_node", matches="\\w+")
- verify: json_path(path="$.current_node", equals="")
- returns: always returns a `CheckpointPosition` object with `current_node` and
  `waiting_on` fields populated from recognized checkpoint formats, or both fields
  set to `""` when input cannot be parsed or does not match expected schemas.
- code: groom/groom/checkpoints.py::parse_position
- tests: groom/tests/test_checkpoints.py::test_pyflow_position_uses_state_and_waiting_on
- tests: groom/tests/test_checkpoints.py::test_retired_position_uses_current_id
- tests: groom/tests/test_checkpoints.py::test_malformed_or_wrongly_typed_position_is_empty

The parser recognizes two checkpoint formats by inspecting the `engine` field:

- **pyflow format** (engine == "pyflow"): extracts `state` into `current_node` and
  `waiting_on` into the gate context path.
- **retired format** (engine absent or other): extracts `current_id` into
  `current_node` and leaves `waiting_on` as `""`.

Input validation normalizes non-string values and missing fields to empty strings.
The function accepts any input — empty, malformed JSON, non-JSON text — and never
raises.

- input: raw JSON-formatted text from checkpoint files; accepts any string,
  including empty, malformed, or non-JSON values.
- output: always returns a `CheckpointPosition` object; never raises.
- callers: [sidecar snapshot](sidecar-snapshot.md) `_current_node()` method,
  [workflow discovery scan](workflow-discovery-scan.md) volume fallback reader,
  dashboard app progress-frame handler for live state updates.

