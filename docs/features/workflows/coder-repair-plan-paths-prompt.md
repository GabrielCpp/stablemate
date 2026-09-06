---
type: format
slug: coder-repair-plan-paths-prompt
title: Coder repair-plan-paths prompt
---
# Coder repair-plan-paths prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/repair-plan-paths.md`
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::refine`
- detail: [coder development flow](flows/coder-dev.md)
- detail: [coder plan result](coder-plan-result.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_unresolvable_service_path_reworks_the_plan`

The path-repair envelope is a low-power string repair for a plan structure rejected by the
deterministic validator. It checks only the rejected repository, service path, implementation
order, or plan-file values against the tree, corrects those values, leaves the plan's design and
other text unchanged, and returns the full replacement `PlanResult` structure. It is not a new
planning pass.

## Fields

### story_path
- type: string path
- required: true
- semantics: story whose plan structure is being repaired
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: directory containing the plan artifacts and path projection
- verify: json_path(path="$.spec_dir", matches=".+")

### review_notes
- type: string
- required: true
- semantics: validator findings naming the plan values that must be corrected
- verify: json_path(path="$.review_notes", matches=".+")

### epic
- type: string
- default: empty string
- required: false
- semantics: epic identity used by the repair commit protocol
- verify: json_path(path="$.epic", matches=".*")

### story_slug
- type: string
- required: true
- semantics: story slug used to identify the plan being repaired
- verify: json_path(path="$.story_slug", matches=".+")

### story_id
- type: string
- required: true
- semantics: story identifier used as the repair commit trailer identity
- verify: json_path(path="$.story_id", matches=".+")

### result_schema
- type: string
- required: true
- semantics: rendered JSON contract the reply must satisfy as a `PlanResult`
- verify: json_path(path="$.result_schema", matches=".+")
