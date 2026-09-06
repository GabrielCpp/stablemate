---
type: format
slug: inbox-jsonl
title: Run inbox JSONL
---
# Run inbox JSONL

The run inbox is an append-oriented JSON-lines file at `<run_dir>/inbox.jsonl`. Each non-empty
line is one `Message`; reads preserve the file, appends write one new line, and replies rewrite
the complete set through a temporary file followed by replacement. Unknown message fields are
retained for workflow-specific classifications and failure diagnostics.

- file: `<run_dir>/inbox.jsonl`
- code: `workhorse/workhorse/inbox.py::Message`
- detail: [run inbox](concepts/run-inbox.md)
- tests: `workhorse/tests/test_inbox.py::test_extra_fields_survive_a_round_trip`

## Fields

### id
- type: string
- required: true
- semantics: stable caller-supplied message identity
- verify: json_path(path="$.id", matches=".+")
- code: `workhorse/workhorse/inbox.py::Message`

### body
- type: string
- required: true
- semantics: message or failure-handoff text
- verify: json_path(path="$.body", matches=".*")
- code: `workhorse/workhorse/inbox.py::Message`

### at
- type: string
- required: true
- semantics: message creation timestamp
- verify: json_path(path="$.at", matches=".+")
- code: `workhorse/workhorse/inbox.py::Message`

### reply
- type: string
- default: empty string
- required: true
- semantics: response text
- verify: json_path(path="$.reply", matches=".+")
- semantics: an empty reply identifies an outstanding message
- verify: json_path(path="$.reply", equals="")
- code: `workhorse/workhorse/inbox.py::Message`

### replied_at
- type: string
- default: empty string
- required: true
- semantics: timestamp paired with a stored reply
- verify: json_path(path="$.replied_at", equals="")
- code: `workhorse/workhorse/inbox.py::Message`

### extra
- type: arbitrary JSON fields
- required: false
- semantics: workflow-defined data carried through validation and round trips
- verify: json_path(path="$.kind", equals="failure")
- code: `workhorse/workhorse/inbox.py::Message`
