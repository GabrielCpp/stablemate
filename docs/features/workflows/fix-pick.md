---
type: format
slug: fix-pick
title: Coder fix selection result
---
# Coder fix selection result

- file: none — in-memory fix-drain result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick`
- detail: [coder backlog contract](concepts/coder-backlog-contract.md)

The result identifies the first drainable item in the coder-filed backlog, or records why the
drain is empty. Blocked items remain in the backlog and are not selected.

## Fields

### has_fix
- type: boolean
- default: false
- required: false
- semantics: whether a non-blocked coder backlog item was selected
- verify: json_path(path="$.has_fix", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.has_fix`

### fix_bullet_id
- type: string
- default: empty string
- required: false
- semantics: bracketed identifier of the selected backlog item
- verify: json_path(path="$.fix_bullet_id", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.fix_bullet_id`

### fix_bullet_text
- type: string
- default: empty string
- required: false
- semantics: selected backlog description without its bracketed identifier
- verify: json_path(path="$.fix_bullet_text", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.fix_bullet_text`

### reason
- type: string
- default: empty string
- required: false
- semantics: explanation when selection did not produce a fix
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.reason`
