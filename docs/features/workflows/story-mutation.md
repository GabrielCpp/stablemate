---
type: format
slug: story-mutation
title: Story mutation result
---
# Story mutation result

The result of a standalone story graph mutation. It distinguishes an idempotent no-op from a
change and identifies the affected epic, story directory, document, and reason.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`
- detail: [author main story processing](concepts/author-main-story-processing.md)

## Fields

### changed
- type: boolean
- default: false
- required: false
- semantics: whether the requested mutation changed the story graph
- verify: json_path(path="$.changed", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`

### epic
- type: string
- default: empty string
- required: false
- semantics: parent epic identifier
- verify: json_path(path="$.epic", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`

### story_slug
- type: string
- default: empty string
- required: false
- semantics: target story identifier
- verify: json_path(path="$.story_slug", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`

### story_dir
- type: string path
- default: empty string
- required: false
- semantics: target story directory
- verify: json_path(path="$.story_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`

### story_path
- type: string path
- default: empty string
- required: false
- semantics: target story document path
- verify: json_path(path="$.story_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`

### reason
- type: string
- default: empty string
- required: false
- semantics: explanation of the mutation or no-op
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`
