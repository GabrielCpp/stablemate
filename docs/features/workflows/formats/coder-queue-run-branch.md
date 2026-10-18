---
type: format
slug: coder-queue-run-branch
title: Coder queue run branch
---
# Coder queue run branch

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::RunBranch` @d94ba7a3bcb5
- detail: [coder shared library](../concepts/coder-shared-library.md)

The run-branch result names the one `feat/` branch a pr-mode run lands every item on, and the
base its pull requests target. A commit-mode run cuts no branch and produces no such result.

## Fields

### base_branch
- type: string
- default: `""`
- required: false
- semantics: the docs repository's active branch when the run started, or its trunk when that branch is itself a `feat/` or `rewrite/` branch
- verify: json_path(path="$.base_branch", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::RunBranch` @d94ba7a3bcb5

### branch
- type: string
- default: `""`
- required: false
- semantics: `feat/<name>`, where the name is the story slug for a story launch, the epic for a single-epic launch, or the run id otherwise
- verify: json_path(path="$.branch", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::RunBranch` @d94ba7a3bcb5
