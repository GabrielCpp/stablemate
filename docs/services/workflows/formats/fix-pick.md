---
type: format
slug: fix-pick
title: Coder fix selection result
---
# Coder fix selection result

- file: none, because it is an in-memory fix-drain result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick` @80910fc81473
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)
- detail: [debt register](../../ostler/concepts/the-debt-register.md)

The result carries the oldest open `qa` record of the run's workspace repositories on the debt
register, or records why the drain is dry. Selection reads the register and changes nothing on it.
Records filed by any other filer are never selected.

## Fields

### has_fix
- type: boolean
- default: false
- required: false
- semantics: whether an open `qa` record of a workspace repository was drawn
- verify: json_path(path="$.has_fix", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.has_fix` @80910fc81473

### record_id
- type: string
- default: empty string
- required: false
- semantics: full id of the drawn record, which is also its folder name on the register
- verify: json_path(path="$.record_id", equals="X-1")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.record_id` @80910fc81473

### repo
- type: string
- default: empty string
- required: false
- semantics: workspace repository the drawn record names
- verify: json_path(path="$.repo", equals="api-service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.repo` @80910fc81473

### area
- type: string
- default: empty string
- required: false
- semantics: area folder of the drawn record inside its repository
- verify: json_path(path="$.area", equals="billing")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.area` @80910fc81473

### summary
- type: string
- default: empty string
- required: false
- semantics: one-line summary of the drawn record, which the owner turn receives as the item text
- verify: json_path(path="$.summary", equals="first item")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.summary` @80910fc81473

### body
- type: string
- default: empty string
- required: false
- semantics: markdown body of the drawn record, which the fix story's Context section repeats
- verify: json_path(path="$.body", equals="The total drops the last cent.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.body` @80910fc81473

### reason
- type: string
- default: empty string
- required: false
- semantics: the drawn id on a draw, or the repositories searched when no open `qa` record is left
- verify: json_path(path="$.reason", equals="drew 'X-1' from the register")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixPick.reason` @80910fc81473
