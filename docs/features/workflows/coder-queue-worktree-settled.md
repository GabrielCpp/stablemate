---
type: format
slug: coder-queue-worktree-settled
title: Coder queue worktree settled
---
# Coder queue worktree settled

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeSettled`
- detail: [coder shared library](concepts/coder-shared-library.md)

The settled-worktree result is the agent's decision about paths left after a story. `settled`
allows the workflow to continue; `blocked` parks the run for an operator rather than committing
work whose ownership or recording is unclear.

## Fields

### status
- type: literal `settled` | `blocked`
- required: true
- semantics: whether the shown worktree state is safely recorded or needs an operator decision
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeSettled`
- detail: [coder queue worktree settled field roles](concepts/coder-queue-worktree-settled-field-roles.md)

### notes
- type: string
- default: `""`
- required: false
- semantics: per-package record of committed paths or reasons paths were deliberately left
- verify: json_path(path="$.notes", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeSettled`
- detail: [coder queue worktree settled field roles](concepts/coder-queue-worktree-settled-field-roles.md)
