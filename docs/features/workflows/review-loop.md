---
type: format
slug: review-loop
title: Coder review loop state
---
# Coder review loop state

- file: none — checkpointed review state parameter
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewLoop`
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- detail: [coder review flow](flows/coder-review.md)

`ReviewLoop` carries the three counters needed to resume and bound one review flow. `rework`
resets when operator resolution starts a fresh review round; `blocks` is cumulative; and
`session_turns` includes the inherited implementation conversation and recycles at eight.

## Fields

### rework
- type: integer
- default: 0
- required: false
- semantics: apply passes spent on the current review round
- verify: json_path(path="$.rework", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewLoop.rework`

### blocks
- type: integer
- default: 0
- required: false
- semantics: cumulative trips through the operator gate, including resolver answers
- verify: json_path(path="$.blocks", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewLoop.blocks`

### session_turns
- type: integer
- default: 0
- required: false
- semantics: implementation conversation turns spent by review and development lanes
- verify: json_path(path="$.session_turns", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewLoop.session_turns`
- tests: `workflows/tests/coder/test_session_chains.py::test_a_conversation_that_fills_up_inside_the_review_lane_is_recycled`

### COUNT_LABELS
- type: `tuple[str, ...]`
- default: `("rework", "blocks", "session_turns")`
- required: true
- semantics: span dimension names emitted for the three review counters before the `review.` prefix is added
- verify: count(subject="review loop counter labels", equals=3)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewLoop.COUNT_LABELS`
