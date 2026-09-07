---
type: concept
slug: epic-split-review-field-roles
title: Epic split review field roles
---
# Epic split review field roles

`EpicSplitReview` defines both `status` and `notes` as required fields. `status` is the
machine-readable verdict that selects validation, rework, or operator resolution; `notes` carries
the review findings that explain that verdict to the rework or operator context.

Neither field supersedes the other. Consumers use `status` to route the review and use `notes` to
preserve its rationale, so a complete review reads both fields together.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitReview`
- rule: use `status` to select the review path and `notes` to carry the findings for that path
