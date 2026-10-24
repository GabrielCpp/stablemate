---
type: format
slug: fix-story-seed
title: Coder fix story seed result
---
# Coder fix story seed result

- file: none, because it is an in-memory fix-story seed result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed` @46f582904d54
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)
- detail: [debt register](../../ostler/concepts/the-debt-register.md)

The result records the story created or reused for one drained register record, including the
epic and story paths the fix flow needs. A story whose covers already holds the record id is
reused, so a resumed run seeds no second story.

## Fields

### epic
- type: string
- default: empty string
- required: false
- semantics: fix epic containing the seeded story
- verify: json_path(path="$.epic", equals="acme-epic")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.epic` @46f582904d54

### epic_dir
- type: string
- default: empty string
- required: false
- semantics: resolved directory of the fix epic
- verify: json_path(path="$.epic_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.epic_dir` @46f582904d54

### story_slug
- type: string
- default: empty string
- required: false
- semantics: slug of the story created or reused for the item
- verify: json_path(path="$.story_slug", equals="acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.story_slug` @46f582904d54

### story_dir
- type: string
- default: empty string
- required: false
- semantics: resolved story directory
- verify: json_path(path="$.story_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.story_dir` @46f582904d54

### story_path
- type: string
- default: empty string
- required: false
- semantics: resolved story document path
- verify: json_path(path="$.story_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.story_path` @46f582904d54

### record_id
- type: string
- default: empty string
- required: false
- semantics: full id of the register record that seeded this story, which the story's covers holds
- verify: json_path(path="$.record_id", equals="X-1")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.record_id` @46f582904d54

### reason
- type: string
- default: empty string
- required: false
- semantics: explanation of story reuse or creation
- verify: json_path(path="$.reason", equals="The slice works without it.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/backlog.py::FixStorySeed.reason` @46f582904d54
