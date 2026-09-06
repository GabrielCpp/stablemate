---
type: format
slug: split-result
title: Survey split result
---
# Survey split result

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SplitResult`
- detail: [shared survey library](concepts/survey-shared-library.md)

The result of replacing an oversized folder unit with eligible immediate children.

## Fields

### split_ok
- type: boolean
- default: false
- required: false
- semantics: whether the folder was replaced successfully
- verify: json_path(path="$.split_ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SplitResult`

### children_count
- type: integer
- default: 0
- required: false
- semantics: number of child units inserted by the split
- verify: json_path(path="$.children_count", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SplitResult`

### split_errors
- type: string
- default: empty string
- required: false
- semantics: diagnostic reason the split could not be performed
- verify: json_path(path="$.split_errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SplitResult`
