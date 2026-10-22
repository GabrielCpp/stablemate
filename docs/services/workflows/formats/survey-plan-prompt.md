---
type: format
slug: survey-plan-prompt
title: Survey plan prompt contract
---
# Survey plan prompt contract

- file: `workflows/src/workhorse_workflows/author/surveyor/prompts/plan-units.md`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PlanResult` @7db58efbfd66
- detail: [author surveyor subflow](../concepts/author-surveyor-subflow.md)
- tests: `workflows/tests/author/surveyor/test_flow.py::test_two_components_are_planned_assessed_verified_and_emitted`

The planner receives the rubric and survey paths, decides the assessable unit granularity, and
writes mechanical enumeration rules rather than an explicit unit list. Existing rules and
operator context are inputs to a rework decision; expansion later rejects empty or invalid rules.

## Fields

### rubric
- type: string path
- required: true
- semantics: readable survey concern that defines the in-scope units and assessment standard
- verify: json_path(path="$.rubric", equals="example rubric")

### rules_path
- type: string path
- required: true
- semantics: YAML artifact receiving non-empty folder, file, or command enumeration rules
- verify: json_path(path="$.rules_path", equals="docs/stories/acme-story/story.md")

### context_path
- type: string path
- required: true
- semantics: optional operator context consulted for prior answers
- verify: json_path(path="$.context_path", equals="docs/stories/acme-story/story.md")

### plan_errors
- type: string
- default: empty string
- required: false
- semantics: deterministic expansion errors supplied when rules must be repaired
- verify: json_path(path="$.plan_errors", equals="example plan errors")

### status
- type: string
- default: empty string
- required: false
- semantics: reply outcome, `complete` when rules were written or `blocked` when a scope decision is needed
- verify: json_path(path="$.status", equals="example status")

### notes
- type: string
- default: empty string
- required: false
- semantics: explanation of the granularity choice or the blocking question
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
