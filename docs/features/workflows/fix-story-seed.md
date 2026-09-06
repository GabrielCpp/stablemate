---
type: format
slug: fix-story-seed
title: Coder fix story seed result
---
# Coder fix story seed result

- file: none — in-memory fix-story seed result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed`
- detail: [coder backlog contract](concepts/coder-backlog-contract.md)

The result records the story created or reused for one backlog item, including the epic and
story paths needed by the fix flow.

## Fields

### epic
- type: string
- default: empty string
- required: false
- semantics: fix epic containing the seeded story
- verify: json_path(path="$.epic", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.epic`

### epic_dir
- type: string
- default: empty string
- required: false
- semantics: resolved directory of the fix epic
- verify: json_path(path="$.epic_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.epic_dir`

### story_slug
- type: string
- default: empty string
- required: false
- semantics: slug of the story created or reused for the item
- verify: json_path(path="$.story_slug", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.story_slug`

### story_dir
- type: string
- default: empty string
- required: false
- semantics: resolved story directory
- verify: json_path(path="$.story_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.story_dir`

### story_path
- type: string
- default: empty string
- required: false
- semantics: resolved story document path
- verify: json_path(path="$.story_path", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.story_path`

### bullet_id
- type: string
- default: empty string
- required: false
- semantics: backlog identifier that seeded this story
- verify: json_path(path="$.bullet_id", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.bullet_id`

### reason
- type: string
- default: empty string
- required: false
- semantics: explanation of story reuse or creation
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.reason`
