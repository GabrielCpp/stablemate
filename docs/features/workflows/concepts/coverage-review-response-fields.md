---
type: concept
slug: coverage-review-response-fields
title: Coverage review response fields
---
# Coverage review response fields

`CoverageReview` declares `status` and `notes` as separate optional string fields. Both remain
current: the schema contains no deprecation, delegation, or preference between them. A coverage
review response can therefore carry its lifecycle result in `status` and its review context in
`notes` at the same time.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::CoverageReview`
- rule: use `status` for the review lifecycle result and `notes` for review context; neither field replaces the other
