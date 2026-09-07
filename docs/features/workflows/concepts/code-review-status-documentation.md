---
type: concept
slug: code-review-status-documentation
title: Code review status documentation
---
# Code review status documentation

`CodeReviewResult.status` is one required `CodeReviewStatus` value. Its schema description
distinguishes `findings` for an issue-bearing review, `clean` for a reviewed diff with no issues,
`skipped` for no local changes, and `blocked` for a diff that cannot be read.

The field has two current documentation contexts. The code-review result is the reference for the
typed result returned by the review pass. The code-review prompt is the reference for the feeder
reviewer's required reply that produces that result. Neither context replaces the other: the
schema declares one required field and no deprecation or source-backed ranking between the two
documents.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.status`
- rule: use the result field to understand the returned review record and the prompt field to understand the feeder reviewer's reply; both describe the same required schema field
