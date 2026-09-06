---
type: format
slug: coder-queue-base-branch
title: Coder queue base branch
---
# Coder queue base branch

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::BaseBranch`
- detail: [coder shared library](concepts/coder-shared-library.md)

The base-branch result carries the branch against which an epic pull request is opened. The
producer prefers the attached non-work branch and resolves a repository trunk when needed.

## Fields

### base_branch
- type: string
- default: `""`
- required: false
- semantics: selected non-empty branch name used as the epic integration base
- verify: json_path(path="$.base_branch", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::BaseBranch`
