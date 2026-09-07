---
type: format
slug: impl-result
title: Coder implementation result
---
# Coder implementation result

- file: none — agent reply and checkpoint value
- config: `ImplResult` implementation-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### status
- type: literal `done`, `applied`, `no_changes_needed`, `needs_changes`, or `blocked`
- required: true
- semantics: implementation outcome reported by the turn
- verify: json_path(path="$.status", matches="done|applied|no_changes_needed|needs_changes|blocked")
- semantics: only `blocked` routes directly to a block
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult.status`
- detail: [implementation result status](concepts/implementation-result-status.md)

### notes
- type: `str`
- default: empty string
- required: false
- semantics: implementation, verification, or blocking explanation
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult.notes`
- detail: [implementation result notes](concepts/impl-result-notes.md)
