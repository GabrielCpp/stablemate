---
type: format
slug: story-source
title: Coder story source
---
# Coder story source

- file: none — in-memory source provenance record
- config: `StorySource` source-root entry
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource` @5aa622da8aea
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### repo
- type: `str`
- default: empty string
- required: false
- semantics: implementation repository name
- verify: json_path(path="$.repo", equals="api-service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.repo` @5aa622da8aea

### checkout
- type: `str`
- default: empty string
- required: false
- semantics: filesystem checkout path
- verify: json_path(path="$.checkout", equals="example checkout")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.checkout` @5aa622da8aea

### surface
- type: `str`
- default: empty string
- required: false
- semantics: dispatched service surface identifier
- verify: json_path(path="$.surface", equals="example surface")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.surface` @5aa622da8aea

### root
- type: `str`
- default: `.`
- required: false
- semantics: source root relative to the checkout
- verify: json_path(path="$.root", equals="docs/stories")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.root` @5aa622da8aea

### base
- type: `str`
- default: empty string
- required: false
- semantics: earliest commit associated with the story
- verify: json_path(path="$.base", equals="example base")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.base` @5aa622da8aea

### head
- type: `str`
- default: `WORKTREE`
- required: false
- semantics: source head marker used for the current worktree
- verify: json_path(path="$.head", equals="example head")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.head` @5aa622da8aea
