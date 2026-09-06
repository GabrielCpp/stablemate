---
type: format
slug: story-split-done
title: Story split completion
---
# Story split completion

The terminal value returned after one epic's story topology passes mechanical coverage validation
and semantic review.

- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone`
- detail: [author story-split subflow](concepts/story-split-subflow.md)
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`

## Fields

### status
- type: literal `accepted`
- default: `accepted`
- required: true
- semantics: terminal disposition indicating the story graph was accepted
- verify: json_path(path="$.status", equals="accepted")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone`

### epic
- type: string
- required: true
- semantics: explicitly selected epic whose stories were split
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone`

### epic_dir
- type: string path
- required: true
- semantics: canonical repository-relative directory containing the selected epic
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone`

### receipt_path
- type: string path
- required: true
- semantics: repository-relative path to the digest-bound semantic review receipt
- verify: json_path(path="$.receipt_path", matches="story-split-receipt\\.json$")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone`

### coverage_reworks
- type: integer
- default: 0
- required: true
- semantics: number of coverage-driven story split rework passes
- verify: json_path(path="$.coverage_reworks", equals=0)
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone`

### operator_resolutions
- type: integer
- default: 0
- required: true
- semantics: number of operator-resolution turns used by the split flow
- verify: json_path(path="$.operator_resolutions", equals=0)
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone`
