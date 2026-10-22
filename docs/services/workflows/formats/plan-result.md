---
type: format
slug: plan-result
title: Survey plan reply
---
# Survey plan reply

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PlanResult` @7db58efbfd66
- detail: [author surveyor subflow](../concepts/author-surveyor-subflow.md)

The planner's structured response. `status` is either `complete` or `blocked`.

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: planner outcome, `complete` or `blocked`
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PlanResult` @7db58efbfd66
- detail: [plan result fields](../concepts/plan-result-fields.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: planner explanation, rules, or blocking information
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PlanResult` @7db58efbfd66
- detail: [plan result fields](../concepts/plan-result-fields.md)
