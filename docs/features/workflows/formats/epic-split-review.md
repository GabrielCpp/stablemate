---
type: format
slug: epic-split-review
title: Epic split review
---
# Epic split review

The review is the independent verdict over the milestone's ordered epic skeletons.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitReview` @38f4bbac59ba
- detail: [author epic split subflow](../concepts/author-epic-split-subflow.md)

## Fields

### status
- type: literal `approved`, `needs_rework`, or `blocked`
- required: true
- semantics: independent review verdict drawn from the literal set `approved`, `needs_rework`, or `blocked`
- verify: json_path(path="$.status", equals="approved")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitReview` @38f4bbac59ba
- detail: [epic split review field roles](../concepts/epic-split-review-field-roles.md)

### notes
- type: string
- required: true
- semantics: review findings describing exact repairs or the owner decision required
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitReview` @38f4bbac59ba
- detail: [epic split review field roles](../concepts/epic-split-review-field-roles.md)
