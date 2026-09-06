---
type: format
slug: coder-queue-story-committed
title: Coder queue story committed
---
# Coder queue story committed

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryCommitted`
- detail: [coder shared library](concepts/coder-shared-library.md)

The commit result distinguishes implementation work from the separate documentation status
stamp. It reports implementation commits only, and records whether the passing stamp replaced a
previous attempt outcome.

## Fields

### committed
- type: boolean
- default: `false`
- required: false
- semantics: whether implementation work was committed in any affected repository
- verify: json_path(path="$.committed", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryCommitted`

### superseded_outcome
- type: boolean
- default: `false`
- required: false
- semantics: whether the passing status replaced a prior non-default story outcome
- verify: json_path(path="$.superseded_outcome", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryCommitted`
