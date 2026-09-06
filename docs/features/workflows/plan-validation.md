---
type: format
slug: plan-validation
title: Coder plan validation
---
# Coder plan validation

- file: none — in-memory plan validation result
- config: `PlanValidation` result from `record_plan`
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanValidation`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### status
- type: literal `valid` or `invalid`
- default: `valid`
- required: false
- semantics: whether the projected plan points at valid services and files
- verify: json_path(path="$.status", matches="valid|invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanValidation.status`

### errors
- type: `list[str]`
- default: empty list
- required: false
- semantics: deterministic validation failures handed to plan refinement
- verify: json_path(path="$.errors", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanValidation.errors`

### document
- type: `dict[str, Any]`
- default: empty mapping
- required: false
- semantics: projected plan document written to `plan-context.json`
- verify: json_path(path="$.document", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanValidation.document`
