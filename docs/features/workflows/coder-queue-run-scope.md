---
type: format
slug: coder-queue-run-scope
title: Coder queue run scope
---
# Coder queue run scope

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::RunScope`
- detail: [coder shared library](concepts/coder-shared-library.md)

The fresh-run result records which stale run-scoped queue ledgers were removed before processing
starts. A resumed run does not re-enter this operation.

## Fields

### cleared
- type: list of strings
- default: `[]`
- required: false
- semantics: ledger filenames removed from the run directory, in removal order
- verify: count(subject="cleared ledgers", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::RunScope`
