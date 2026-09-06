---
type: format
slug: coverage-review
title: Story split coverage review
---
# Story split coverage review

The independent semantic verdict over one epic's seed-to-story coverage after mechanical
validation.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::CoverageReview`
- detail: [author story-split subflow](concepts/story-split-subflow.md)

## Fields

### status
- type: string; `ok`, `blocked`, or a rework status
- default: empty string
- required: true
- semantics: selects receipt recording, operator resolution, or story rework
- verify: json_path(path="$.status", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::CoverageReview`

### notes
- type: string
- default: empty string
- required: true
- semantics: review findings passed to story splitting or the operator context
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::CoverageReview`
