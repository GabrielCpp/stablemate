---
type: format
slug: review-feedback
title: Coder review feedback
---
# Coder review feedback

- file: none — in-memory inbox poll result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::Feedback` @818036e1a230
- detail: [coder review schema contracts](../concepts/coder-review-schema-contracts.md)
- detail: [coder review shared nodes](../concepts/coder-review-shared-review.md)
- detail: [workflow kit run inbox](../../workhorse/concepts/operator-inbox.md)

Feedback is the non-blocking operator note the QA check polls once after a passing run. If
present, the note goes back to the QA owner as a repair report; if absent, the check goes on to
its next gate.

## Fields

### present
- type: boolean
- default: false
- required: false
- semantics: whether an outstanding inbox note was found
- verify: json_path(path="$.present", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::Feedback.present` @818036e1a230

### content
- type: `str`
- default: empty string
- required: false
- semantics: operator note handed to the QA owner on its next turn
- verify: json_path(path="$.content", equals="Please recheck the login flow.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::Feedback.content` @818036e1a230
