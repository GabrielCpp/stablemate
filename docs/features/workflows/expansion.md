---
type: format
slug: expansion
title: Survey inventory expansion result
---
# Survey inventory expansion result

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion`
- detail: [shared survey library](concepts/survey-shared-library.md)

The result of consuming or materializing the survey unit inventory.

## Fields

### expand_ok
- type: boolean
- default: false
- required: false
- semantics: whether the inventory is usable
- verify: json_path(path="$.expand_ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion`
- detail: [expansion result field roles](concepts/expansion-result-field-roles.md)

### expand_errors
- type: string
- default: empty string
- required: false
- semantics: diagnostic expansion failure text
- verify: json_path(path="$.expand_errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion`
- detail: [expansion result field roles](concepts/expansion-result-field-roles.md)

### unit_count
- type: integer
- default: 0
- required: false
- semantics: number of units in the resulting inventory
- verify: json_path(path="$.unit_count", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion`
- detail: [expansion result field roles](concepts/expansion-result-field-roles.md)

### inventory_note
- type: string
- default: empty string
- required: false
- semantics: explanation of whether the inventory was reused or expanded
- verify: json_path(path="$.inventory_note", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion`
- detail: [expansion result field roles](concepts/expansion-result-field-roles.md)
