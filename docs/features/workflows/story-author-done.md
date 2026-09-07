---
type: format
slug: story-author-done
title: Story author completion
---
# Story author completion

- The completion value identifies the directly authored story, carries an optional mockup path and
  notes, and uses `status: blocked` when autonomous resolution is exhausted; normal completion
  retains the default `status: authored`.

- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryAuthorDone`
- detail: [author story-author subflow](concepts/author-story-author-subflow.md)

## Fields

### status
- type: string
- default: `authored`
- required: true
- semantics: distinguishes normal authored completion from a parked blocked result
- verify: json_path(path="$.status", equals="authored")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryAuthorDone`
- detail: [story author completion field roles](concepts/story-author-done-field-roles.md)

### epic
- type: string
- default: empty string
- required: true
- semantics: parent epic of the authored story
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryAuthorDone`
- detail: [story author completion field roles](concepts/story-author-done-field-roles.md)

### story
- type: string
- default: empty string
- required: true
- semantics: authored story slug
- verify: json_path(path="$.story", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryAuthorDone`
- detail: [story author completion field roles](concepts/story-author-done-field-roles.md)

### story_path
- type: repository-relative string path
- default: empty string
- required: true
- semantics: path to the authored story document
- verify: json_path(path="$.story_path", matches="/story\\.md$")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryAuthorDone`
- detail: [story author completion field roles](concepts/story-author-done-field-roles.md)

### mockup
- type: string path or empty string
- default: empty string
- required: true
- semantics: story-local mockup reference carried through authoring
- verify: json_path(path="$.mockup", matches=".*")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryAuthorDone`
- detail: [story author completion field roles](concepts/story-author-done-field-roles.md)

### notes
- type: string
- default: empty string
- required: true
- semantics: blocking or audit notes returned with the result
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryAuthorDone`
- detail: [story author completion field roles](concepts/story-author-done-field-roles.md)
