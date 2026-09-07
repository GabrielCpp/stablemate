---
type: format
slug: coder-queue-story-pick
title: Coder queue story pick
---
# Coder queue story pick

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder shared library](concepts/coder-shared-library.md)

The story-pick result is the main-loop merge guard. `story` dispatches implementation, `done`
permits pruning and merge, and `blocked` sets the epic aside. The pessimistic default is
`blocked`.

## Fields

### story_outcome
- type: literal `story` | `done` | `blocked`
- default: `"blocked"`
- required: false
- semantics: next main-loop branch decision for the epic
- verify: json_path(path="$.story_outcome", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)

### story_path
- type: string path
- default: `""`
- required: false
- semantics: selected story document path
- verify: json_path(path="$.story_path", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)

### spec_dir
- type: string path
- default: `""`
- required: false
- semantics: directory containing the selected story specification
- verify: json_path(path="$.spec_dir", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)

### story_slug
- type: string
- default: `""`
- required: false
- semantics: selected story slug
- verify: json_path(path="$.story_slug", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)

### story_id
- type: string
- default: `""`
- required: false
- semantics: minted story identifier used in commit trailers, when present
- verify: json_path(path="$.story_id", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)

### epic
- type: string
- default: `""`
- required: false
- semantics: epic whose story queue was inspected
- verify: json_path(path="$.epic", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)

### reason
- type: string
- default: `""`
- required: false
- semantics: explanation for selection, completion, blocking, or unreadable queue state
- verify: json_path(path="$.reason", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)

### progress
- type: string
- default: `""`
- required: false
- semantics: completed and total story worklist snapshot
- verify: json_path(path="$.progress", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)

### remaining_count
- type: integer
- default: `0`
- required: false
- semantics: number of stories still remaining in the epic report
- verify: json_path(path="$.remaining_count", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryPick`
- detail: [coder queue story pick field roles](concepts/coder-queue-story-pick-field-roles.md)
