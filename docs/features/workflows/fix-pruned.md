---
type: format
slug: fix-pruned
title: Coder pruned fix result
---
# Coder pruned fix result

- file: none — in-memory fix-drain result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPruned`
- detail: [coder backlog contract](concepts/coder-backlog-contract.md)

The result records whether the shipped fix's backlog bullet was removed.

## Fields

### pruned
- type: boolean
- default: false
- required: false
- semantics: whether the matching backlog bullet was removed
- verify: json_path(path="$.pruned", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPruned.pruned`

### bullet_id
- type: string
- default: empty string
- required: false
- semantics: identifier of the bullet targeted for removal
- verify: json_path(path="$.bullet_id", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPruned.bullet_id`

### reason
- type: string
- default: empty string
- required: false
- semantics: explanation of the prune outcome
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPruned.reason`
