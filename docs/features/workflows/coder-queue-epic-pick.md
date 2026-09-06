---
type: format
slug: coder-queue-epic-pick
title: Coder queue epic pick
---
# Coder queue epic pick

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPick`
- detail: [coder shared library](concepts/coder-shared-library.md)

The epic-pick result distinguishes a selected front epic from an empty or entirely set-aside
queue. `reason` carries the distinction when no epic is selected.

## Fields

### has_epic
- type: boolean
- default: `false`
- required: false
- semantics: whether an epic is available for the next main-loop pass
- verify: json_path(path="$.has_epic", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPick`

### epic
- type: string
- default: `""`
- required: false
- semantics: identifier of the selected epic
- verify: json_path(path="$.epic", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPick`

### reason
- type: string
- default: `""`
- required: false
- semantics: explanation for selection failure, queue exhaustion, or all epics being set aside
- verify: json_path(path="$.reason", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPick`
