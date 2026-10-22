---
type: format
slug: story-split-done
title: Story split completion
---
# Story split completion

The terminal value returned after one epic's story split either passes mechanical coverage validation
and the PM review, or stays blocked.

- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone` @3d9f15f6170b
- detail: [author story-split subflow](../concepts/story-split-subflow.md)
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`

## Fields

### status
- type: literal `accepted` or `blocked`
- default: `accepted`
- required: false
- semantics: `accepted` when the story graph passed the lint and the PM review, `blocked` when a rework or answer budget ran out
- verify: json_path(path="$.status", equals="accepted")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone` @3d9f15f6170b
- detail: [story split completion field roles](../concepts/story-split-done-field-roles.md)

### epic
- type: string
- required: true
- semantics: explicitly selected epic whose stories were split
- verify: json_path(path="$.epic", equals="acme-epic")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone` @3d9f15f6170b
- detail: [story split completion field roles](../concepts/story-split-done-field-roles.md)

### epic_dir
- type: string path
- required: true
- semantics: canonical repository-relative directory containing the selected epic
- verify: json_path(path="$.epic_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone` @3d9f15f6170b
- detail: [story split completion field roles](../concepts/story-split-done-field-roles.md)

### notes
- type: string
- default: empty
- required: false
- semantics: the findings or question that left the split blocked
- verify: json_path(path="$.notes", equals="")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone` @3d9f15f6170b
- detail: [story split completion field roles](../concepts/story-split-done-field-roles.md)

### reworks
- type: integer
- default: 0
- required: false
- semantics: number of rework passes the splitter made
- verify: json_path(path="$.reworks", equals=0)
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone` @3d9f15f6170b
- detail: [story split completion field roles](../concepts/story-split-done-field-roles.md)

### answers
- type: integer
- default: 0
- required: false
- semantics: number of PM answers the splitter used
- verify: json_path(path="$.answers", equals=0)
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone` @3d9f15f6170b
- detail: [story split completion field roles](../concepts/story-split-done-field-roles.md)
