---
type: format
slug: emit-result
title: Survey emission result
---
# Survey emission result

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)

The result of writing generated backlog bullets and survey traceability.

## Fields

### emit_ok
- type: boolean
- default: false
- required: false
- semantics: whether both survey artifacts were emitted successfully
- verify: json_path(path="$.emit_ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult`

### emit_errors
- type: string
- default: empty string
- required: false
- semantics: diagnostic emission failure text
- verify: json_path(path="$.emit_errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult`

### bullet_count
- type: integer
- default: 0
- required: false
- semantics: number of backlog bullets emitted from validated clusters
- verify: json_path(path="$.bullet_count", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult`

### emit_note
- type: string
- default: empty string
- required: false
- semantics: human-readable emission outcome note
- verify: json_path(path="$.emit_note", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult`
