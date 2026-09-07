---
type: format
slug: story-author-target
title: Story author target
---
# Story author target

- The target identifies one caller-selected story and the canonical repository-relative paths used
  by every story-author prompt.

- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget`
- detail: [author story-author subflow](concepts/author-story-author-subflow.md)

## Fields

### epic
- type: string
- default: empty string
- required: true
- semantics: trimmed parent epic slug used to resolve the story
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget`
- detail: [story author target field roles](concepts/story-author-target-field-roles.md)

### story
- type: string
- default: empty string
- required: true
- semantics: trimmed story slug resolved under `epic`
- verify: json_path(path="$.story", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget`
- detail: [story author target field roles](concepts/story-author-target-field-roles.md)

### epic_dir
- type: repository-relative string path
- default: empty string
- required: true
- semantics: canonical directory containing the selected epic
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget`
- detail: [story author target field roles](concepts/story-author-target-field-roles.md)

### story_dir
- type: repository-relative string path
- default: empty string
- required: true
- semantics: canonical directory containing the selected story document
- verify: json_path(path="$.story_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget`
- detail: [story author target field roles](concepts/story-author-target-field-roles.md)

### story_path
- type: repository-relative string path
- default: empty string
- required: true
- semantics: canonical path to the selected `story.md`
- verify: json_path(path="$.story_path", matches="/story\\.md$")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget`
- detail: [story author target field roles](concepts/story-author-target-field-roles.md)

### scaffolded
- type: boolean
- default: false
- required: true
- semantics: indicates that the preparation operation completed the required scaffold pass
- verify: json_path(path="$.scaffolded", equals=true)
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget`
- detail: [story author target field roles](concepts/story-author-target-field-roles.md)

### scaffold_message
- type: string
- default: empty string
- required: true
- semantics: Ostler's scaffold result message
- verify: json_path(path="$.scaffold_message", matches=".*")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget`
- detail: [story author target field roles](concepts/story-author-target-field-roles.md)
