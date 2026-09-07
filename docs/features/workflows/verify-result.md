---
type: format
slug: verify-result
title: Survey verification result
---
# Survey verification result

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult`
- detail: [shared survey library](concepts/survey-shared-library.md)

The auditable coverage-gate result for the survey inventory.

## Fields

### holds
- type: boolean
- default: false
- required: false
- semantics: whether every current unit has acceptable coverage
- verify: json_path(path="$.holds", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult`
- detail: [verify result field roles](concepts/verify-result-field-roles.md)

### nothing_surveyed
- type: boolean
- default: false
- required: false
- semantics: whether the missing inventory means no units were surveyed
- verify: json_path(path="$.nothing_surveyed", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult`
- detail: [verify result field roles](concepts/verify-result-field-roles.md)

### verify_errors
- type: string
- default: empty string
- required: false
- semantics: coverage defects preventing the gate from holding
- verify: json_path(path="$.verify_errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult`
- detail: [verify result field roles](concepts/verify-result-field-roles.md)

### verify_report
- type: string
- default: empty string
- required: false
- semantics: human-readable coverage counts and outcome
- verify: json_path(path="$.verify_report", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::VerifyResult`
- detail: [verify result field roles](concepts/verify-result-field-roles.md)
