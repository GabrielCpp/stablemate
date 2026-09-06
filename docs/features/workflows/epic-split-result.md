---
type: format
slug: epic-split-result
title: Epic split result
---
# Epic split result

The result is the structured reply returned by the split and rework agent turns.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult`
- detail: [author epic split subflow](concepts/author-epic-split-subflow.md)

## Fields

### status
- type: literal `complete` or `blocked`
- required: true
- semantics: whether the agent completed the requested split or cannot proceed
- verify: json_path(path="$.status", equals="complete")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult`

### notes
- type: string
- required: true
- semantics: agent explanation passed to review or operator resolution
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult`
