---
type: concept
slug: coder-review-schema-contracts
title: Coder review schema contracts
---
# Coder review schema contracts

The `coder.shared.schemas.review` module defines the typed values exchanged by the review flow:
the feeder review result, binding verdict, review context, inbox feedback, checkpointed budgets,
and terminal result. Agent-produced statuses are closed literals and must be present; fields
produced by the flow use conservative defaults where the flow owns the value.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::__all__`
- detail: [coder review flow](../flows/coder-review.md)
- detail: [coder finding](../finding.md)
- detail: [coder result routing contract](coder-result-routing.md)
- detail: [coder review finding](../review-finding.md)
- detail: [coder code review result](../code-review-result.md)
- detail: [coder review verdict](../review-verdict.md)
- detail: [coder review context](../review-context.md)
- detail: [coder review feedback](../review-feedback.md)
- detail: [coder review loop state](../review-loop.md)
- detail: [coder review result](../review-result.md)

`ReviewCategory` closes finding lenses to `Bug`, `Standard`, and `Reuse`. `CodeReviewStatus`
distinguishes findings, a clean checked diff, no affected changes, and an unreadable diff.
`ReviewStatus` distinguishes approval, required changes, and an external block. The review flow
uses `ReviewLoop` to checkpoint local rework, cumulative operator blocks, and the shared
implementation conversation turn count.
