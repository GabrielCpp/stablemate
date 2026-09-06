---
type: format
slug: story-split-agent-result
title: Story split agent result
---
# Story split agent result

The agent result controls whether the selected epic's stories are accepted for coverage checking
or whether the turn is blocked or declines the requested rework.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StorySplit`
- detail: [author story-split subflow](concepts/story-split-subflow.md)

## Fields

### status
- type: string; `blocked`, `standoff`, or any non-blocked completion status
- default: empty string
- required: true
- semantics: selects coverage checking, the coverage gate, or the normal continuation
- verify: json_path(path="$.status", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StorySplit`

### notes
- type: string
- default: empty string
- required: true
- semantics: agent findings passed to a gate or the next rework turn
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StorySplit`
