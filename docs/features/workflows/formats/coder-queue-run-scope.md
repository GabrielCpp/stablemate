---
type: format
slug: coder-queue-run-scope
title: Coder queue run scope
---
# Coder queue run scope

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::RunScope` @d94ba7a3bcb5
- detail: [coder shared library](../concepts/coder-shared-library.md)

The fresh-run result records which stale run-scoped files a previous run left in the run
directory, the worklist and the answer log, and which of them were removed before the launch is
filed. An empty run directory name removes nothing.

## Fields

### cleared
- type: list of strings
- default: `[]`
- required: false
- semantics: the names of the worklist and answer log files removed from the run directory
- verify: count(subject="cleared run files", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::RunScope` @d94ba7a3bcb5
