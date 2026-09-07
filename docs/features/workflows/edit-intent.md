---
type: format
slug: edit-intent
title: Author edit intent
---
# Author edit intent

The edit intent is the typed binding contract between story-level validation and epic reconciliation.
It identifies whether the requested operation adds or removes a story, names the affected epic and
story or source bullet, preserves backlog provenance, carries the human change reason, and records
whether destructive scope is explicitly forced. It is an in-memory payload, not an on-disk file.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [author story edit subflow](concepts/author-story-edit-subflow.md)

## Fields

### kind
- type: `Literal["epic", "add-story", "remove-story"]`
- default: `epic`
- required: false
- semantics: identifies the edit operation consumed by epic reconciliation
- verify: json_path(path="$.kind", equals="add-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [edit intent field roles](concepts/edit-intent-field-roles.md)

### epic
- type: string
- default: empty string
- required: false
- semantics: names the parent epic
- verify: json_path(path="$.epic", matches=".+")
- semantics: story removal obtains the parent epic from the existing story
- verify: json_path(path="$.kind", equals="remove-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [edit intent field roles](concepts/edit-intent-field-roles.md)

### story
- type: string
- default: empty string
- required: false
- semantics: names the story selected for removal
- verify: json_path(path="$.story", equals="")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [edit intent field roles](concepts/edit-intent-field-roles.md)

### bullet_id
- type: string
- default: empty string
- required: false
- semantics: identifies the backlog or literal source item covered by an added story
- verify: json_path(path="$.bullet_id", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [edit intent field roles](concepts/edit-intent-field-roles.md)

### source_bullet
- type: string
- default: empty string
- required: false
- semantics: preserves the resolved source bullet text for the added story
- verify: json_path(path="$.source_bullet", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [edit intent field roles](concepts/edit-intent-field-roles.md)

### from_backlog
- type: boolean
- default: false
- required: false
- semantics: records whether the source bullet came from the configured backlog
- verify: json_path(path="$.from_backlog", equals=True)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [edit intent field roles](concepts/edit-intent-field-roles.md)

### change
- type: string
- default: empty string
- required: false
- semantics: carries the supplied reason, or the operation-specific generated reason
- verify: json_path(path="$.change", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [edit intent field roles](concepts/edit-intent-field-roles.md)

### force
- type: boolean
- default: false
- required: false
- semantics: authorizes destructive reconciliation that the normal safety checks reject
- verify: json_path(path="$.force", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- detail: [edit intent field roles](concepts/edit-intent-field-roles.md)
