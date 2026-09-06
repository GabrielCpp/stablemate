---
type: format
slug: story-choice
title: Author story choice
---
# Author story choice

The selection result for the next story an author flow should process. `has_story` distinguishes
an available story from an exhausted or invalid queue; the remaining fields identify the selected
story and expose dependency-order progress.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`
- detail: [author main story processing](concepts/author-main-story-processing.md)

## Fields

### has_story
- type: boolean
- default: false
- required: false
- semantics: whether a story was selected
- verify: json_path(path="$.has_story", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`

### story_path
- type: string path
- default: empty string
- required: false
- semantics: path to the selected story document
- verify: json_path(path="$.story_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`

### story_slug
- type: string
- default: empty string
- required: false
- semantics: selected story identifier
- verify: json_path(path="$.story_slug", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`

### story_dir
- type: string path
- default: empty string
- required: false
- semantics: directory containing the selected story
- verify: json_path(path="$.story_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`

### reason
- type: string
- default: empty string
- required: false
- semantics: selection or exhaustion explanation
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`

### progress
- type: string
- default: empty string
- required: false
- semantics: human-readable completed and remaining progress
- verify: json_path(path="$.progress", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`

### remaining_count
- type: integer
- default: 0
- required: false
- semantics: count of stories still needing authoring
- verify: json_path(path="$.remaining_count", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`
