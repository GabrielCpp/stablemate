---
type: format
slug: review-feedback
title: Coder review feedback
---
# Coder review feedback

- file: none — in-memory inbox poll result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::Feedback`
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- detail: [coder review shared nodes](concepts/coder-review-shared-review.md)
- detail: [workflow kit run inbox](../workhorse/concepts/run-inbox.md)

Feedback is the non-blocking operator note polled after approval or settlement. If present, the
review flow consumes it and spends exactly one apply pass; if absent, the flow returns its result.

## Fields

### present
- type: boolean
- default: false
- required: false
- semantics: whether an outstanding inbox note was found
- verify: json_path(path="$.present", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::Feedback.present`

### content
- type: `str`
- default: empty string
- required: false
- semantics: operator note supplied to the review apply turn
- verify: json_path(path="$.content", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::Feedback.content`
- tests: `workflows/tests/coder/review/test_flow.py::test_dropped_feedback_buys_exactly_one_rework_pass`
