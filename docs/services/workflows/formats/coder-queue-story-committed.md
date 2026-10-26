---
type: format
slug: coder-queue-story-committed
title: Coder queue story committed
---
# Coder queue story committed

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryCommitted` @5263a86ab920
- detail: [coder shared library](../concepts/coder-shared-library.md)

Two operations return this result. Committing a completed story commits its changes in each
affected code repository and then stamps the story's status. Recording the plan commits only what
the run wrote into the spec directory, and does nothing when that directory is outside the docs
repository. The `committed` field reports code or plan commits only, and `superseded_outcome`
records whether the passing stamp replaced a previous attempt outcome.

## Fields

### committed
- type: boolean
- default: `false`
- required: false
- semantics: whether a commit landed in any affected repository, or in the docs repository for a plan record
- verify: json_path(path="$.committed", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryCommitted` @5263a86ab920
- detail: [coder queue story committed field roles](../concepts/coder-queue-story-committed-field-roles.md)

### superseded_outcome
- type: boolean
- default: `false`
- required: false
- semantics: whether the passing status replaced a prior non-default story outcome
- verify: json_path(path="$.superseded_outcome", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryCommitted` @5263a86ab920
- detail: [coder queue story committed field roles](../concepts/coder-queue-story-committed-field-roles.md)
