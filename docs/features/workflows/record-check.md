---
type: format
slug: record-check
title: Survey record check
---
# Survey record check

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordCheck`
- detail: [shared survey library](concepts/survey-shared-library.md)

The deterministic validation outcome for one finding record.

## Fields

### record_ok
- type: boolean
- default: false
- required: false
- semantics: whether the selected unit's record is complete and internally consistent
- verify: json_path(path="$.record_ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordCheck`
- detail: [record check field roles](concepts/record-check-field-roles.md)

### record_errors
- type: string
- default: empty string
- required: false
- semantics: diagnostic validation errors for the record
- verify: json_path(path="$.record_errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordCheck`
- detail: [record check field roles](concepts/record-check-field-roles.md)
