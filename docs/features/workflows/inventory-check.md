---
type: format
slug: inventory-check
title: Survey inventory check
---
# Survey inventory check

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::InventoryCheck`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)

The decision returned before expansion: whether the planner must define unit rules.

## Fields

### needs_plan
- type: boolean
- default: false
- required: false
- semantics: true only when neither a frozen inventory nor pinned rules exist
- verify: json_path(path="$.needs_plan", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::InventoryCheck`

### check_note
- type: string
- default: empty string
- required: false
- semantics: human-readable explanation of the selected inventory precedence branch
- verify: json_path(path="$.check_note", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::InventoryCheck`
