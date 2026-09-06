---
type: format
slug: mark-result
title: Survey mark result
---
# Survey mark result

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult`
- detail: [shared survey library](concepts/survey-shared-library.md)

The result of stamping an inventory unit from its finding record.

## Fields

### marked
- type: boolean
- default: false
- required: false
- semantics: whether the matching inventory entry was written
- verify: json_path(path="$.marked", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult`

### unit_status
- type: string
- default: empty string
- required: false
- semantics: status read from or assigned to the finding record
- verify: json_path(path="$.unit_status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult`

### mark_note
- type: string
- default: empty string
- required: false
- semantics: diagnostic or outcome note for the mark operation
- verify: json_path(path="$.mark_note", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult`
