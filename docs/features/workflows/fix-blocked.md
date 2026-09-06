---
type: format
slug: fix-blocked
title: Coder blocked fix result
---
# Coder blocked fix result

- file: none — in-memory fix-drain result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixBlocked`
- detail: [coder backlog contract](concepts/coder-backlog-contract.md)

The result records whether a backlog bullet is now marked blocked. An already blocked bullet is
reported as marked without being rewritten.

## Fields

### marked
- type: boolean
- default: false
- required: false
- semantics: whether the targeted bullet is blocked after the operation
- verify: json_path(path="$.marked", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixBlocked.marked`

### bullet_id
- type: string
- default: empty string
- required: false
- semantics: identifier of the bullet targeted for blocking
- verify: json_path(path="$.bullet_id", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixBlocked.bullet_id`

### reason
- type: string
- default: empty string
- required: false
- semantics: reason recorded with the blocked annotation
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixBlocked.reason`
