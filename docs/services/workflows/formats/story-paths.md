---
type: format
slug: story-paths
title: Story paths
---
# Story paths

The story preparation result carries the canonical absolute paths and identities used by every
per-story Coder lane. Story and epic inputs are resolved through the configured Ostler document
root; the QA directory is derived beneath the resolved spec directory. An empty story slug
produces an all-blank result for standalone execution, including an empty story identity.

- file: none — in-memory workflow result
- config: Ostler document roots and the supplied story/epic inputs
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::StoryPaths` @ae123b24b397
- detail: [Coder story pipeline](../concepts/story-pipeline.md)

## Fields

### story_path
- type: `str`
- default: empty string
- required: false
- semantics: absolute path to the selected epic story document
- verify: json_path(path="$.story_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::StoryPaths.story_path` @ae123b24b397

### spec_dir
- type: `str`
- default: empty string
- required: false
- semantics: absolute directory for the story's plan and evidence artifacts
- verify: json_path(path="$.spec_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::StoryPaths.spec_dir` @ae123b24b397

### qa_dir
- type: `str`
- default: empty string
- required: false
- semantics: `qa` subdirectory directly beneath the resolved spec directory
- verify: json_path(path="$.qa_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::StoryPaths.qa_dir` @ae123b24b397

### story_slug
- type: `str`
- default: empty string
- required: false
- semantics: requested story slug
- verify: json_path(path="$.story_slug", equals="acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::StoryPaths.story_slug` @ae123b24b397

### story_epic
- type: `str`
- default: empty string
- required: false
- semantics: supplied epic name, or the first epic containing the story when epic input is absent
- verify: json_path(path="$.story_epic", equals="acme-epic")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::StoryPaths.story_epic` @ae123b24b397

### story_id
- type: `str`
- default: empty string
- required: false
- semantics: minted story identity used for commit trailers
- verify: json_path(path="$.story_id", equals="CASE-1234")
- semantics: empty when the story has no minted id
- verify: json_path(path="$.story_id", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/story.py::StoryPaths.story_id` @ae123b24b397
