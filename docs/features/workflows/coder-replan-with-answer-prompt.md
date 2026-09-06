---
type: format
slug: coder-replan-with-answer-prompt
title: Coder replan-with-answer prompt
---
# Coder replan-with-answer prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/replan-with-answer.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev.rework_plan`
- detail: [coder development flow](flows/coder-dev.md)
- detail: [coder plan result](coder-plan-result.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_blocked_plan_goes_to_the_auto_operator_and_is_reworked`

This re-planning envelope re-enters a blocked plan with an operator answer already written in the
story context. It limits edits to the affected plan sections, preserves the existing plan shape
and unchanged text, incorporates the answer into the plan, and returns the complete replacement
`PlanResult` structure. It does not implement code or rediscover a different story.

## Fields

### story_path
- type: string path
- required: true
- semantics: story document whose plan is being revised
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: directory containing the plan files to revise
- verify: json_path(path="$.spec_dir", matches=".+")

### review_notes
- type: string
- required: true
- semantics: original plan block that explains which decision needs the answer
- verify: json_path(path="$.review_notes", matches=".+")

### operator_context
- type: string
- required: true
- semantics: authoritative operator answer folded into the revised plan
- verify: json_path(path="$.operator_context", matches=".+")

### epic
- type: string
- default: empty string
- required: false
- semantics: epic identity used by the plan's commit protocol
- verify: json_path(path="$.epic", matches=".*")

### story_slug
- type: string
- required: true
- semantics: story slug used to identify the plan being revised
- verify: json_path(path="$.story_slug", matches=".+")

### story_id
- type: string
- required: true
- semantics: story identifier used as the plan commit trailer identity
- verify: json_path(path="$.story_id", matches=".+")

### result_schema
- type: string
- required: true
- semantics: rendered JSON contract the reply must satisfy as a `PlanResult`
- verify: json_path(path="$.result_schema", matches=".+")
