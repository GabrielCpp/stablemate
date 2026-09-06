---
type: format
slug: coverage-defects
title: Story split coverage defects
---
# Story split coverage defects

The mechanical coverage validator's result for the selected epic. It is successful only when no
coverage-specific doctor errors remain.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Defects`
- detail: [author story-split subflow](concepts/story-split-subflow.md)

## Fields

### ok
- type: boolean
- default: false
- required: true
- semantics: true when the selected epic has no relevant coverage defect
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Defects`

### errors
- type: string
- default: empty string
- required: true
- semantics: newline-separated coverage findings, empty on success
- verify: json_path(path="$.errors", equals="")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Defects`
