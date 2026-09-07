---
type: format
slug: coder-queue-epic-branch
title: Coder queue epic branch
---
# Coder queue epic branch

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBranch`
- detail: [coder shared library](concepts/coder-shared-library.md)

The epic-branch result records the epic selected by the main loop and its `feat/` branch name.

## Fields

### working_epic
- type: string
- default: `""`
- required: false
- semantics: epic identifier whose branch is active
- verify: json_path(path="$.working_epic", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBranch`
- detail: [coder queue epic branch field roles](concepts/coder-queue-epic-branch-field-roles.md)

### epic_branch
- type: string
- default: `""`
- required: false
- semantics: branch name formed as `feat/<epic>`
- verify: json_path(path="$.epic_branch", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBranch`
- detail: [coder queue epic branch field roles](concepts/coder-queue-epic-branch-field-roles.md)
