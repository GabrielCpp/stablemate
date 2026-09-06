---
type: format
slug: epic-split-validation
title: Epic split validation
---
# Epic split validation

The validation result reports whether the split satisfies the ordered, skeleton-only boundary and
which milestone and epics were observed.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitValidation`
- detail: [author epic split subflow](concepts/author-epic-split-subflow.md)

## Fields

### ok
- type: boolean
- default: false
- required: true
- semantics: true only when every epic-split invariant passes
- verify: json_path(path="$.ok", equals=False)
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitValidation`

### milestone_path
- type: string repository-relative path
- default: empty string
- required: true
- semantics: validated roadmap-owned milestone path, or empty when no unique match exists
- verify: json_path(path="$.milestone_path", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitValidation`

### ordered_epics
- type: list of strings
- default: empty list
- required: true
- semantics: non-empty milestone epic names in their authored order when a unique milestone exists
- verify: json_path(path="$.ordered_epics", equals=[])
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitValidation`

### errors
- type: string
- default: empty string
- required: true
- semantics: newline-separated validation findings
- verify: json_path(path="$.errors", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitValidation`
