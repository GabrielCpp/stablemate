---
type: format
slug: applied-epic-edit
title: Applied epic edit
---
# Applied epic edit

The result of applying an approved epic edit plan. It records whether the graph changed, the epic
identity and directory, whether the epic was deleted, and the ordered story sets subsequent
rewriting and coverage stages consume.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- detail: [author epic edit subflow](concepts/author-epic-edit-subflow.md)

## Fields

### changed
- type: boolean
- default: false
- required: false
- semantics: whether application changed the graph
- verify: json_path(path="$.changed", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- detail: [applied epic edit field roles](concepts/applied-epic-edit-field-roles.md)

### epic
- type: string
- default: empty string
- required: false
- semantics: applied epic identifier
- verify: json_path(path="$.epic", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- detail: [applied epic edit field roles](concepts/applied-epic-edit-field-roles.md)

### epic_dir
- type: string path
- default: empty string
- required: false
- semantics: directory of the surviving epic
- verify: json_path(path="$.epic_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- detail: [applied epic edit field roles](concepts/applied-epic-edit-field-roles.md)

### deleted
- type: boolean
- default: false
- required: false
- semantics: whether application deleted the epic
- verify: json_path(path="$.deleted", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- detail: [applied epic edit field roles](concepts/applied-epic-edit-field-roles.md)

### affected_stories
- type: list of strings
- default: empty list
- required: false
- semantics: surviving stories requiring downstream processing
- verify: json_path(path="$.affected_stories", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- detail: [applied epic edit field roles](concepts/applied-epic-edit-field-roles.md)

### removed_stories
- type: list of strings
- default: empty list
- required: false
- semantics: stories removed by the approved edit
- verify: json_path(path="$.removed_stories", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- detail: [applied epic edit field roles](concepts/applied-epic-edit-field-roles.md)
