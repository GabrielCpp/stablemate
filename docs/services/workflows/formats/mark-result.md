---
type: format
slug: mark-result
title: Survey mark result
---
# Survey mark result

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult` @59f51b5b79f1
- detail: [shared survey library](../concepts/survey-shared-library.md)

The result of stamping an inventory unit from its finding record.

## Fields

### marked
- type: boolean
- default: false
- required: false
- semantics: whether the matching inventory entry was written
- verify: json_path(path="$.marked", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult` @59f51b5b79f1
- detail: [mark result field roles](../concepts/mark-result-field-roles.md)

### unit_status
- type: string
- default: empty string
- required: false
- semantics: status read from or assigned to the finding record
- verify: json_path(path="$.unit_status", equals="example unit status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult` @59f51b5b79f1
- detail: [mark result field roles](../concepts/mark-result-field-roles.md)

### mark_note
- type: string
- default: empty string
- required: false
- semantics: diagnostic or outcome note for the mark operation
- verify: json_path(path="$.mark_note", equals="example mark note")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult` @59f51b5b79f1
- detail: [mark result field roles](../concepts/mark-result-field-roles.md)
