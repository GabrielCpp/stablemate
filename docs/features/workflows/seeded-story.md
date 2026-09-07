---
type: format
slug: seeded-story
title: Seeded story result
---
# Seeded story result

The result of registering one backlog or literal bullet as a story. It carries the created or
reused story paths, the source bullet identity, provenance, and the reason for the outcome.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- detail: [author main story processing](concepts/author-main-story-processing.md)

## Fields

### epic_dir
- type: string path
- default: empty string
- required: false
- semantics: epic directory receiving the seeded story
- verify: json_path(path="$.epic_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- detail: [seeded story field roles](concepts/seeded-story-field-roles.md)

### story_slug
- type: string
- default: empty string
- required: false
- semantics: created or reused story identifier
- verify: json_path(path="$.story_slug", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- detail: [seeded story field roles](concepts/seeded-story-field-roles.md)

### story_dir
- type: string path
- default: empty string
- required: false
- semantics: directory of the created or reused story
- verify: json_path(path="$.story_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- detail: [seeded story field roles](concepts/seeded-story-field-roles.md)

### story_path
- type: string path
- default: empty string
- required: false
- semantics: story document path
- verify: json_path(path="$.story_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- detail: [seeded story field roles](concepts/seeded-story-field-roles.md)

### bullet_id
- type: string
- default: empty string
- required: false
- semantics: source backlog or literal bullet identifier
- verify: json_path(path="$.bullet_id", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- detail: [seeded story field roles](concepts/seeded-story-field-roles.md)

### from_backlog
- type: boolean
- default: false
- required: false
- semantics: whether the source bullet came from the configured backlog
- verify: json_path(path="$.from_backlog", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- detail: [seeded story field roles](concepts/seeded-story-field-roles.md)

### reason
- type: string
- default: empty string
- required: false
- semantics: explanation of creation or reuse
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- detail: [seeded story field roles](concepts/seeded-story-field-roles.md)
