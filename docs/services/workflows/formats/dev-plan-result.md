---
type: format
slug: dev-plan-result
title: Coder development plan result
---
# Coder development plan result

The dev owner replies with this claim at the end of the plan phase. It says the plan files are
written and committed, or names the one question that blocks the plan.

- file: none, agent reply and checkpoint value
- config: `PlanResult` plan phase output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::PlanResult` @4ed65104b9b1
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)
- detail: [coder dev-plan prompt](coder-dev-plan-prompt.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_fresh_story_runs_plan_build_and_review_in_that_order`

## Fields

### status
- type: literal `ready` or `blocked`
- required: true
- semantics: `ready` when `plan.md` and its service files are written and committed, `blocked` when only the operator can decide
- verify: json_path(path="$.status", matches="ready|blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::PlanResult.status` @4ed65104b9b1

### notes
- type: `str`
- default: empty string
- required: false
- semantics: what the plan decided and where it is recorded, or on `blocked` the one question that would unblock it
- verify: json_path(path="$.notes", equals="Planned the change in plan.md.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::PlanResult.notes` @4ed65104b9b1
