---
type: concept
slug: coder-review-package
title: Coder review package
---
# Coder review package

The `review` machine independently judges one story's implementation, applies unresolved findings,
and offers bounded repair cycles for failed gates. It is a sub-flow entered by the Coder main flow
after QA passes, and can also be run directly with `workhorse-coder run review`.

The flow partitions code review findings into product defects, architecture concerns, and
refactoring suggestions. Product defects block the story and trigger repairs; architecture
concerns and suggestions are rendered and delegated to an operator gate. Repair cycles are
bounded per defect kind; exhausted repairs escalate to an operator gate. The flow's routing
controls and label management are defined by the `Review` class.

- code: `workflows/src/workhorse_workflows/coder/review/flow.py`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review`
- tests: `workflows/tests/coder/test_review.py::test_one_clean_independent_review_and_apply_cycle`
- detail: [coder review shared review](coder-review-shared-review.md)

