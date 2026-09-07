---
type: format
slug: verify-report
title: Author verification report
---
# Author verification report

The shared report returned by reconciliation and integrity verification keeps the gate decision
separate from whether the check was skipped. `report` preserves the resolver-facing explanation.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### holds
- type: boolean
- default: false
- required: false
- semantics: whether the verification condition holds or is allowed through as skipped
- verify: json_path(path="$.holds", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport`
- detail: [verify report field roles](concepts/verify-report-field-roles.md)

### skipped
- type: boolean
- default: false
- required: false
- semantics: whether verification could not run because its prerequisite was unavailable
- verify: json_path(path="$.skipped", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport`
- detail: [verify report field roles](concepts/verify-report-field-roles.md)

### errors
- type: string
- default: empty string
- required: false
- semantics: verification findings presented to the author flow
- verify: json_path(path="$.errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport`
- detail: [verify report field roles](concepts/verify-report-field-roles.md)

### report
- type: string
- default: empty string
- required: false
- semantics: multi-line verification preamble supplied to the resolver prompt
- verify: json_path(path="$.report", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::VerifyReport`
- detail: [verify report field roles](concepts/verify-report-field-roles.md)
