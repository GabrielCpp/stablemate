---
type: format
slug: coder-queue-story-stamped
title: Coder queue story stamped
---
# Coder queue story stamped

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryStamped`
- detail: [coder shared library](concepts/coder-shared-library.md)

The story-stamped result records the queue-integrity status write that marks a passing story and
whether that write replaced a previous attempt outcome.

## Fields

### stamped
- type: boolean
- default: `false`
- required: false
- semantics: whether the story's `QA passed` status was written
- verify: json_path(path="$.stamped", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryStamped`

### superseded_outcome
- type: boolean
- default: `false`
- required: false
- semantics: whether the passing status replaced a prior non-default story outcome
- verify: json_path(path="$.superseded_outcome", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryStamped`
