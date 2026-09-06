---
type: format
slug: coder-plan-story-prompt
title: Coder plan-story prompt
---
# Coder plan-story prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/plan-story.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev.start`
- detail: [coder development flow](flows/coder-dev.md)
- detail: [coder plan result](coder-plan-result.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_plans_stamps_branches_and_implements_every_layer`

The planning envelope tells an agent to plan exactly the supplied authored story, read only the
standards and code paths relevant to its layers, write the plan artifacts under the supplied spec
directory, and return a `PlanResult`. The workflow supplies workspace service markers and the
rendered result schema; the plan's implementation order, test scenarios, verification commands,
and machine-readable service structure are the contract consumed by later development states.

## Fields

### story_path
- type: string path
- required: true
- semantics: authored story document that is the sole planning target
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: directory receiving the root plan and per-service plan artifacts
- verify: json_path(path="$.spec_dir", matches=".+")

### markers
- type: string
- default: empty string
- required: false
- semantics: workspace service-marker guidance used to identify concrete services
- verify: json_path(path="$.markers", matches=".*")

### result_schema
- type: string
- required: true
- semantics: rendered JSON contract the reply must satisfy as a `PlanResult`
- verify: json_path(path="$.result_schema", matches=".+")
