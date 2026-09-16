---
type: format
slug: dev-result
title: Coder development result
---
# Coder development result

- file: none — in-memory development-flow result
- config: `DevResult` parent-flow handoff
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DevResult` @b6e19c205b4f
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### status
- type: literal `ready` or `replan`
- default: `ready`
- required: false
- semantics: whether development is ready for the next lane or requires replanning
- verify: json_path(path="$.status", matches="ready|replan")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DevResult.status` @b6e19c205b4f

### operator_notes
- type: `str`
- default: empty string
- required: false
- semantics: operator answer text passed back to the parent flow
- verify: json_path(path="$.operator_notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DevResult.operator_notes` @b6e19c205b4f

### session_turns
- type: `int`
- default: `0`
- required: false
- semantics: conversation turns spent when the development flow ended
- verify: json_path(path="$.session_turns", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DevResult.session_turns` @b6e19c205b4f
