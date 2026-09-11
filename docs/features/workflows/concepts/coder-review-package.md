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
- code: `workflows/tests/coder/review/test_flow.py::docs`
- code: `workflows/tests/coder/review/test_flow.py::workspace`
- code: `workflows/tests/coder/review/test_flow.py::test_human_operator_modes_wait_on_the_story_context_file`
- code: `workflows/tests/coder/review/test_flow.py::test_a_resolver_that_grounds_its_answer_settles_a_review_block.never`
- tests: `workflows/tests/coder/review/test_flow.py`
- detail: [coder review shared review](coder-review-shared-review.md)

The `review` flow runs against a docs repository carrying one epic with its `## Stories` listing
and one authored story, and against a workspace file naming the code repositories the review
turns grant themselves. The `docs` and `workspace` test fixtures stand those inputs up —
`docs` builds the docs repo with the epic, the story, and the plan-context the dev flow left
behind, and `workspace` builds two real git repositories with a checked-in `.code-workspace`
file carrying relative paths exactly as a project ships one, since `resolve_review_context`
resolves the affected code repos by name out of that manifest. The fixtures are not the
behaviour under test; the turns they set up run cold against the same artifacts the YAML
engine drove against, so the settlement ledger the apply gate rebuilds against is the same
one the production run would write.

The `human` and `operator` operator modes block on the story context file rather than spend a
resolver turn. `test_human_operator_modes_wait_on_the_story_context_file` proves both
parameterised values reach the operator without a resolver trip. The `never` callback inside
`test_a_resolver_that_grounds_its_answer_settles_a_review_block` asserts an `answered` arm
produced by the auto-resolver must not park the run on the context file — a grounded answer
is consumed at the same point a human's would be, and a resolver that keeps parking is the
defect the assertion catches.

