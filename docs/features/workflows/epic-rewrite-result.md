---
type: format
slug: epic-rewrite-result
title: Epic rewrite result
---
# Epic rewrite result

The rewrite agent reply reports whether the epic prose was rewritten after an applied edit and
preserves the agent's notes.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicRewriteResult`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### status
- type: `Literal["complete", "blocked"]`
- default: blocked
- required: false
- semantics: whether the epic rewrite completed
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicRewriteResult`

### notes
- type: string
- default: empty string
- required: false
- semantics: agent notes accompanying the rewrite outcome
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicRewriteResult`
