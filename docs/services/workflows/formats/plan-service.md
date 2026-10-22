---
type: format
slug: plan-service
title: Coder plan service
---
# Coder plan service

- file: none — in-memory nested plan record
- config: `PlanService` fields returned inside a plan projection
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanService` @bcd75ac6f796
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

One service or shared package changed by a plan. Shared packages omit `plan_file`.

## Fields

### repo
- type: `str`
- default: empty string
- required: false
- semantics: workspace repository containing the service
- verify: json_path(path="$.repo", equals="api-service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanService.repo` @bcd75ac6f796

### path
- type: `str`
- default: empty string
- required: false
- semantics: service path relative to its repository, or `.` for the root
- verify: json_path(path="$.path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanService.path` @bcd75ac6f796

### type
- type: `str`
- default: empty string
- required: false
- semantics: technology key used for service skill and prompt selection
- verify: json_path(path="$.type", equals="example type")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanService.type` @bcd75ac6f796

### plan_file
- type: `str`
- default: empty string
- required: false
- semantics: service plan path relative to the specification directory
- verify: json_path(path="$.plan_file", equals="docs/stories/acme-story/story.md")
- semantics: empty for shared packages
- verify: json_path(path="$.plan_file", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanService.plan_file` @bcd75ac6f796

### new_service
- type: `bool`
- default: `false`
- required: false
- semantics: whether implementation will scaffold a directory that does not yet exist
- verify: json_path(path="$.new_service", matches="true|false")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanService.new_service` @bcd75ac6f796
