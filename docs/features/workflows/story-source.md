---
type: format
slug: story-source
title: Coder story source
---
# Coder story source

- file: none — in-memory source provenance record
- config: `StorySource` source-root entry
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### repo
- type: `str`
- default: empty string
- required: false
- semantics: implementation repository name
- verify: json_path(path="$.repo", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.repo`

### checkout
- type: `str`
- default: empty string
- required: false
- semantics: filesystem checkout path
- verify: json_path(path="$.checkout", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.checkout`

### surface
- type: `str`
- default: empty string
- required: false
- semantics: dispatched service surface identifier
- verify: json_path(path="$.surface", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.surface`

### root
- type: `str`
- default: `.`
- required: false
- semantics: source root relative to the checkout
- verify: json_path(path="$.root", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.root`

### base
- type: `str`
- default: empty string
- required: false
- semantics: earliest commit associated with the story
- verify: json_path(path="$.base", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.base`

### head
- type: `str`
- default: `WORKTREE`
- required: false
- semantics: source head marker used for the current worktree
- verify: json_path(path="$.head", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySource.head`
