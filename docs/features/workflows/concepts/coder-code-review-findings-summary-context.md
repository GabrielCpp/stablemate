---
type: concept
slug: coder-code-review-findings-summary-context
title: Coder code-review findings summary context
---
# Coder code-review findings summary context

`CodeReviewResult.findings_summary` is one string field with an empty default. Its schema
description requires a one-sentence account of flagged issues, or of what stopped a blocked
review.

The field appears in two current documentation contexts. The code-review result describes the
structured result consumed after the review pass. The code-review prompt describes the same
field as part of the feeder turn's required reply. Neither context is a replacement for the
other: the schema declares no deprecation or selection rule between them.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.findings_summary`
- rule: use the result field to understand the returned review record and the prompt field to understand the feeder turn's reply; both describe the same current schema field
