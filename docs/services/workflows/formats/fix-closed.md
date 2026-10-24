---
type: format
slug: fix-closed
title: Coder closed fix result
---
# Coder closed fix result

- file: none, because it is an in-memory fix-drain result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixClosed` @46f582904d54
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)
- detail: [debt register](../../ostler/concepts/the-debt-register.md)

The result records whether the shipped fix's record was closed as `done` on the debt register.
The close reason names each repository that landed a commit of the fix with that commit's short
hash.

## Fields

### closed
- type: boolean
- default: false
- required: false
- semantics: whether the register closed the record as `done`
- verify: json_path(path="$.closed", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixClosed.closed` @46f582904d54

### record_id
- type: string
- default: empty string
- required: false
- semantics: full id of the record the drain tried to close
- verify: json_path(path="$.record_id", equals="X-1")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixClosed.record_id` @46f582904d54

### reason
- type: string
- default: empty string
- required: false
- semantics: the register's message for the close, or the reason nothing was closed when no record id or no landed commit was given
- verify: json_path(path="$.reason", equals="no record or no landed commit — nothing to close")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixClosed.reason` @46f582904d54
