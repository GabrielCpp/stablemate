---
type: format
slug: resolved-bullet
title: Resolved bullet
---
# Resolved bullet

The add-story resolver normalizes an operator's bullet reference into this in-memory source
payload before constructing an [edit intent](edit-intent.md). It records whether the match came
from the configured backlog so later reconciliation can distinguish backlog ownership from a
literal request.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::ResolvedBullet`
- detail: [author story edit subflow](concepts/author-story-edit-subflow.md)

## Fields

### id
- type: string
- default: empty string
- required: false
- semantics: identifies the resolved backlog item or normalized literal bullet
- verify: json_path(path="$.id", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::ResolvedBullet`

### source_bullet
- type: string
- default: empty string
- required: false
- semantics: preserves the source text used as the added story's scope description
- verify: json_path(path="$.source_bullet", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::ResolvedBullet`

### from_backlog
- type: boolean
- default: false
- required: false
- semantics: distinguishes a bullet matched in the configured backlog from a literal or normalized request
- verify: json_path(path="$.from_backlog", equals=True)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::ResolvedBullet`
