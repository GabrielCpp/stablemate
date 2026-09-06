---
type: format
slug: story-change
title: Epic story change
---
# Epic story change

One projected story mutation in an epic edit plan.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
- detail: [epic edit plan](epic-edit-plan.md)

## Fields
### action
- type: `Literal["add", "update", "remove"]`
- default: add
- required: false
- semantics: structural operation applied to the story
- verify: json_path(path="$.action", equals="add")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
### slug
- type: string
- default: empty string
- required: false
- semantics: story identifier
- verify: json_path(path="$.slug", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
### title
- type: string
- default: empty string
- required: false
- semantics: resulting story title
- verify: json_path(path="$.title", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
### covers
- type: list of strings
- default: empty list
- required: false
- semantics: seed identifiers covered by the resulting story
- verify: json_path(path="$.covers", equals=[])
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
### depends
- type: list of strings
- default: empty list
- required: false
- semantics: resulting story dependencies
- verify: json_path(path="$.depends", equals=[])
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
### rewrite
- type: boolean
- default: false
- required: false
- semantics: whether the story body must be rewritten after graph application
- verify: json_path(path="$.rewrite", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
