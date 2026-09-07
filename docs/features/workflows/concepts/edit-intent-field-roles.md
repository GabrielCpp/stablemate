---
type: concept
slug: edit-intent-field-roles
title: Edit intent field roles
---
# Edit intent field roles

`EditIntent` is one request payload, not a set of alternative implementations. The schema
declares all eight fields together, with defaults for every field; it records the operation in
`kind` and carries the operation's identifiers, provenance, rationale, and destructive-action
authorization in their separate fields. There is no source-declared ranking among the fields.

For an epic edit, `kind` remains `epic` and `epic`, `change`, and optionally `force` describe the
request. For a story addition, `kind` is `add-story` and `bullet_id`, `source_bullet`, and
`from_backlog` preserve the source item alongside the epic and change reason. For a story removal,
`kind` is `remove-story` and `story` identifies the selected story; the parent epic is resolved
from that story. Fields outside the selected operation retain their defaults rather than competing
with the fields that describe that operation.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EditIntent`
- code: `workflows/src/workhorse_workflows/author/story_edit/nodes.py::resolve_story_intent`
- rule: select fields by the `kind` of edit; combine the fields required by that operation and do not treat any field as a substitute for another
