---
type: format
slug: feedback
title: Author feedback
---
# Author feedback

Feedback is a non-blocking operator note found in the run inbox. Polling consumes the oldest
outstanding message and gives the author flow one rework pass.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Feedback`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### present
- type: boolean
- default: false
- required: false
- semantics: whether an outstanding feedback message was found
- verify: json_path(path="$.present", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Feedback`

### scope
- type: string
- default: story
- required: false
- semantics: authoring scope named by the feedback message
- verify: json_path(path="$.scope", equals="story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Feedback`

### content
- type: string
- default: empty string
- required: false
- semantics: operator note supplied to the rework prompt
- verify: json_path(path="$.content", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Feedback`
