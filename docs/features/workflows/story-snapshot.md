---
type: format
slug: story-snapshot
title: Epic story snapshot
---
# Epic story snapshot

The baseline metadata and body identity for one story in an epic edit snapshot.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
- detail: [epic edit snapshot](epic-snapshot.md)

## Fields

### slug
- type: string
- default: empty string
- required: false
- semantics: story identifier
- verify: json_path(path="$.slug", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
### title
- type: string
- default: empty string
- required: false
- semantics: story title
- verify: json_path(path="$.title", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
### status
- type: string
- default: empty string
- required: false
- semantics: current story lifecycle status
- verify: json_path(path="$.status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
### covers
- type: list of strings
- default: empty list
- required: false
- semantics: seed identifiers covered by the story
- verify: json_path(path="$.covers", equals=[])
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
### depends
- type: list of strings
- default: empty list
- required: false
- semantics: story dependency slugs
- verify: json_path(path="$.depends", equals=[])
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
### story_path
- type: string path
- default: empty string
- required: false
- semantics: story document path
- verify: json_path(path="$.story_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
### body_hash
- type: string
- default: empty string
- required: false
- semantics: content hash used to protect unaffected story bodies
- verify: json_path(path="$.body_hash", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
### frozen
- type: boolean
- default: false
- required: false
- semantics: whether the story may be changed by the plan
- verify: json_path(path="$.frozen", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
