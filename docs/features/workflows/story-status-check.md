---
type: format
slug: story-status-check
title: Coder story status check
---
# Coder story status check

- file: none — in-memory pre-QA status result
- config: `StoryStatusCheck` status gate result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StoryStatusCheck`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### status
- type: literal `clean` or `dirty`
- default: `dirty`
- required: false
- semantics: whether the story status is safe before QA
- verify: json_path(path="$.status", matches="clean|dirty")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StoryStatusCheck.status`

### written
- type: `str`
- default: empty string
- required: false
- semantics: status text currently written on the story
- verify: json_path(path="$.written", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StoryStatusCheck.written`
