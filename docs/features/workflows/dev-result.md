---
type: format
slug: dev-result
title: Coder development result
---
# Coder development result

- file: none — in-memory development-flow result
- config: `DevResult` parent-flow handoff
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DevResult`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### status
- type: literal `ready` or `replan`
- default: `ready`
- required: false
- semantics: whether development is ready for the next lane or requires replanning
- verify: json_path(path="$.status", matches="ready|replan")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DevResult.status`

### operator_notes
- type: `str`
- default: empty string
- required: false
- semantics: operator answer text passed back to the parent flow
- verify: json_path(path="$.operator_notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DevResult.operator_notes`

### session_turns
- type: `int`
- default: `0`
- required: false
- semantics: conversation turns spent when the development flow ended
- verify: json_path(path="$.session_turns", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DevResult.session_turns`
