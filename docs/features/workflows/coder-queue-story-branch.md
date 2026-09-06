---
type: format
slug: coder-queue-story-branch
title: Coder queue story branch
---
# Coder queue story branch

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryBranch`
- detail: [coder shared library](concepts/coder-shared-library.md)

The story-branch result identifies the branch cut for one story and the repositories where the
branch operation succeeded. Re-running the operation checks out existing branches without reset.

## Fields

### base_branch
- type: string
- default: `""`
- required: false
- semantics: branch read before the story branch was cut
- verify: json_path(path="$.base_branch", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryBranch`

### story_branch
- type: string
- default: `""`
- required: false
- semantics: branch named exactly for the story slug
- verify: json_path(path="$.story_branch", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryBranch`

### repos
- type: list of strings
- default: `[]`
- required: false
- semantics: workspace repository names actually branched, with the documentation repository first
- verify: count(subject="branched repositories", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryBranch`
