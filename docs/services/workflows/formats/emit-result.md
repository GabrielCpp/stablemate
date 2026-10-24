---
type: format
slug: emit-result
title: Survey emission result
---
# Survey emission result

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult` @59f51b5b79f1
- detail: [author surveyor subflow](../concepts/author-surveyor-subflow.md)

The result of filing a survey's findings as records on the [debt register](../../ostler/concepts/the-debt-register.md) and writing survey traceability. The rubric survey and the parity survey both return it.

## Fields

### emit_ok
- type: boolean
- default: false
- required: false
- semantics: whether the records were filed and the manifest was written
- verify: json_path(path="$.emit_ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult` @59f51b5b79f1
- detail: [emit result field roles](../concepts/emit-result-field-roles.md)

### emit_errors
- type: string
- default: empty string
- required: false
- semantics: diagnostic emission failure text
- verify: json_path(path="$.emit_errors", equals="example emit errors")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult` @59f51b5b79f1
- detail: [emit result field roles](../concepts/emit-result-field-roles.md)

### bullet_count
- type: integer
- default: 0
- required: false
- semantics: number of findings the survey stands behind with a record: one per validated cluster for the rubric survey, one per uncovered surface for the parity survey, counting a record a rerun found already on the register
- verify: json_path(path="$.bullet_count", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult` @59f51b5b79f1
- detail: [emit result field roles](../concepts/emit-result-field-roles.md)

### emit_note
- type: string
- default: empty string
- required: false
- semantics: human-readable emission outcome note
- verify: json_path(path="$.emit_note", equals="example emit note")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult` @59f51b5b79f1
- detail: [emit result field roles](../concepts/emit-result-field-roles.md)
