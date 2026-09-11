---
type: format
slug: coder-implement-plan-prompt
title: Coder implement-plan prompt
---
# Coder implement-plan prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/implement-plan.md`
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::implement_layer`
- code: `workflows/tests/coder/test_status_line_ownership.py::test_the_prompt_forbids_writing_the_story_status_line`
- code: `workflows/tests/coder/test_status_line_ownership.py::test_the_guard_names_what_enforces_it`
- detail: [coder development flow](flows/coder-dev.md)
- detail: [coder implementation result](impl-result.md)
- detail: [coder story status check](story-status-check.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_implement_turn_is_handed_the_two_values_its_prompt_reads`
- tests: `workflows/tests/coder/test_status_line_ownership.py::test_the_prompt_forbids_writing_the_story_status_line`
- tests: `workflows/tests/coder/test_status_line_ownership.py::test_the_guard_names_what_enforces_it`

The implementation envelope constrains one turn to the inlined story plan and one selected
service layer. It requires the agent to apply the plan with tests, run the plan's exact
verification commands and service gates, smoke the touched layer when required, and return an
`ImplResult`; a blocked turn is routed to the operator rather than treated as a successful empty
layer. Optional QA setup and operator context are included only when the flow has them.

The prompt carries a `## Story Status` section that names the story's `Implementation Status`
field, prohibits the turn from editing it (one of `Do **not**`, `do **not**`, `exactly as you
found them`), and points at the [coder story status check](story-status-check.md) gate that
re-reads the line after the turn — the gate is what makes stating the rule binding, so a
prohibition without it reads as bookkeeping to an agent that has just decided a story passed
and wants to record it.

## Fields

### story_path
- type: string path
- required: true
- semantics: story whose acceptance criteria define the implementation scope
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: directory containing the story plan and implementation artifacts
- verify: json_path(path="$.spec_dir", matches=".+")

### service_path
- type: string path
- required: true
- semantics: service directory being implemented in the current repository
- verify: json_path(path="$.service_path", matches=".+")

### service_type
- type: string
- required: true
- semantics: service technology used to select its standards and verification behavior
- verify: json_path(path="$.service_type", matches=".+")

### verification
- type: string
- required: true
- semantics: service verification command declared for the selected layer
- verify: json_path(path="$.verification", matches=".+")

### gates
- type: string
- default: empty string
- required: false
- semantics: declared gates that run after implementation, or the explicit no-gates marker
- verify: json_path(path="$.gates", matches=".*")

### qa_run_plan
- type: object or empty value
- default: empty value
- required: false
- semantics: decoded QA setup for touched layers when the implementation needs a local smoke run
- verify: json_path(path="$.qa_run_plan", matches=".*")

### verification_setup
- type: object or empty value
- default: empty value
- required: false
- semantics: story-declared runtime profile and rendering capability for local verification
- verify: json_path(path="$.verification_setup", matches=".*")

### operator_context
- type: string
- default: empty string
- required: false
- semantics: authoritative answer to a prior implementation block, when re-entering the layer
- verify: json_path(path="$.operator_context", matches=".*")

### plan_file
- type: string path
- required: true
- semantics: selected service plan filename within `spec_dir`
- verify: json_path(path="$.plan_file", matches=".+")

### plan_text
- type: string
- required: true
- semantics: complete selected service plan inlined as the implementation instructions
- verify: json_path(path="$.plan_text", matches=".+")

### epic
- type: string
- default: empty string
- required: false
- semantics: epic identity used by the implementation commit protocol
- verify: json_path(path="$.epic", matches=".*")

### story_slug
- type: string
- required: true
- semantics: story slug used by the implementation commit protocol
- verify: json_path(path="$.story_slug", matches=".+")

### story_id
- type: string
- required: true
- semantics: story identifier used as the commit trailer identity
- verify: json_path(path="$.story_id", matches=".+")

### result_schema
- type: string
- required: true
- semantics: rendered JSON contract the reply must satisfy as an `ImplResult`
- verify: json_path(path="$.result_schema", matches=".+")
