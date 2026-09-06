---
type: format
slug: unit-pick
title: Survey unit pick
---
# Survey unit pick

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`
- detail: [shared survey library](concepts/survey-shared-library.md)

The next inventory unit and the snapshot needed to assess it or hand off to coverage.

## Fields

### has_unit
- type: boolean
- default: false
- required: false
- semantics: whether a pending unit was selected
- verify: json_path(path="$.has_unit", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`

### unit_id
- type: string
- default: empty string
- required: false
- semantics: selected inventory unit identifier
- verify: json_path(path="$.unit_id", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`

### unit_path
- type: string
- default: empty string
- required: false
- semantics: source path represented by the selected unit
- verify: json_path(path="$.unit_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`

### unit_kind
- type: string
- default: empty string
- required: false
- semantics: inventory rule kind of the selected unit
- verify: json_path(path="$.unit_kind", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`

### record_path
- type: string path
- default: empty string
- required: false
- semantics: finding-record path derived from the unit identifier
- verify: json_path(path="$.record_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`

### reason
- type: string
- default: empty string
- required: false
- semantics: explanation when no selectable unit exists
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`

### progress
- type: string
- default: empty string
- required: false
- semantics: completed and total unit counts from the selection snapshot
- verify: json_path(path="$.progress", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`

### kinds
- type: string
- default: empty string
- required: false
- semantics: unit-kind counts from the selection snapshot
- verify: json_path(path="$.kinds", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`
