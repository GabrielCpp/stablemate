---
type: format
slug: milestone-validation
title: Milestone validation
---
# Milestone validation

The validation result is the deterministic gate after the agent turn. It reports whether exactly
one roadmap-owned milestone remains valid, identifies that milestone when present, records reuse,
and joins every failure into `errors` for the awaiting state.

- file: none — in-memory Pydantic model
- config: none
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneValidation`
- detail: [author milestone subflow](concepts/author-milestone-subflow.md)
- tests: `workflows/tests/author/milestone/test_flow.py::test_validation_rejects_an_epic_created_by_the_milestone_stage`

## Fields

### ok
- type: boolean
- default: false
- required: false
- semantics: true only when all milestone ownership and immutability checks pass
- verify: json_path(path="$.ok", equals=False)
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneValidation`
- detail: [milestone validation field roles](concepts/milestone-validation-field-roles.md)

### milestone_path
- type: string
- default: empty string when no unique roadmap-owned milestone is found
- required: false
- semantics: repository-relative path of the validated milestone
- verify: json_path(path="$.milestone_path", equals="")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneValidation`
- detail: [milestone validation field roles](concepts/milestone-validation-field-roles.md)

### reused
- type: boolean
- default: false
- required: false
- semantics: records whether preparation found and the flow reused an existing milestone
- verify: json_path(path="$.reused", equals=False)
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneValidation`
- detail: [milestone validation field roles](concepts/milestone-validation-field-roles.md)

### errors
- type: string
- default: empty string
- required: false
- semantics: newline-separated validation failures passed to an awaiting run
- verify: json_path(path="$.errors", equals="")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneValidation`
- detail: [milestone validation field roles](concepts/milestone-validation-field-roles.md)
