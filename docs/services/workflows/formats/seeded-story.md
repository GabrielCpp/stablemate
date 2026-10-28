---
type: format
slug: seeded-story
title: Seeded story result
---
# Seeded story result

The result of registering one [debt register](../../ostler/concepts/the-debt-register.md) record
as a story. It carries the created or reused story paths, the source record id, and the reason for
the outcome.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @b91d7be769de
- detail: [author main story processing](../concepts/author-main-story-processing.md)

## Fields

### epic_dir
- type: string path
- default: empty string
- required: false
- semantics: epic directory receiving the seeded story
- verify: json_path(path="$.epic_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @b91d7be769de
- detail: [seeded story field roles](../concepts/seeded-story-field-roles.md)

### story_slug
- type: string
- default: empty string
- required: false
- semantics: created or reused story identifier
- verify: json_path(path="$.story_slug", equals="acme-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @b91d7be769de
- detail: [seeded story field roles](../concepts/seeded-story-field-roles.md)

### story_dir
- type: string path
- default: empty string
- required: false
- semantics: directory of the created or reused story
- verify: json_path(path="$.story_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @b91d7be769de
- detail: [seeded story field roles](../concepts/seeded-story-field-roles.md)

### story_path
- type: string path
- default: empty string
- required: false
- semantics: story document path
- verify: json_path(path="$.story_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @b91d7be769de
- detail: [seeded story field roles](../concepts/seeded-story-field-roles.md)

### record_id
- type: string
- default: empty string
- required: false
- semantics: id of the register record the story was seeded from
- verify: json_path(path="$.record_id", equals="CASE-1234")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @b91d7be769de
- detail: [seeded story field roles](../concepts/seeded-story-field-roles.md)

### reason
- type: string
- default: empty string
- required: false
- semantics: explanation of creation or reuse
- verify: json_path(path="$.reason", equals="The slice works without it.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @b91d7be769de
- detail: [seeded story field roles](../concepts/seeded-story-field-roles.md)
