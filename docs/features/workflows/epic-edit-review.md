---
type: format
slug: epic-edit-review
title: Epic edit review
---
# Epic edit review

The review reply evaluates the replacement plan after deterministic validation. Only an approved
review proceeds; needs-rework and blocked statuses keep the edit from being applied.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditReview`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### status
- type: `Literal["approved", "needs_rework", "blocked"]`
- default: needs_rework
- required: false
- semantics: review disposition for the epic edit plan
- verify: json_path(path="$.status", equals="needs_rework")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditReview`

### notes
- type: string
- default: empty string
- required: false
- semantics: reviewer explanation accompanying the disposition
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditReview`
