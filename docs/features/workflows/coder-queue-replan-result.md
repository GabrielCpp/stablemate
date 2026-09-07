---
type: format
slug: coder-queue-replan-result
title: Coder queue replan result
---
# Coder queue replan result

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::ReplanResult`
- detail: [coder shared library](concepts/coder-shared-library.md)

The replan result records whether an operator-directed epic rewrite produced a re-grounded epic.
An unresolved answer remains blocked rather than becoming an invented execution plan.

## Fields

### status
- type: literal `done` | `blocked`
- required: true
- semantics: whether the epic was re-grounded or must remain blocked
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::ReplanResult`
- detail: [coder queue replan result field roles](concepts/coder-queue-replan-result-field-roles.md)

### notes
- type: string
- default: `""`
- required: false
- semantics: summary of what was re-grounded or what remained undecided
- verify: json_path(path="$.notes", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::ReplanResult`
- detail: [coder queue replan result field roles](concepts/coder-queue-replan-result-field-roles.md)
