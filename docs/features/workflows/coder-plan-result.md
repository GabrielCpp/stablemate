---
type: format
slug: coder-plan-result
title: Coder plan result
---
# Coder plan result

- file: none — agent reply and checkpoint value
- config: `PlanResult` agent output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanResult`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### status
- type: literal `done` or `blocked`
- required: true
- semantics: whether the plan was produced and is ready for review, or could not be produced
- verify: json_path(path="$.status", matches="done|blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanResult.status`

### summary
- type: `str`
- default: empty string
- required: false
- semantics: one-line plan description or blocker
- verify: json_path(path="$.summary", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanResult.summary`

### services
- type: `list[PlanService]`
- default: empty list
- required: false
- semantics: services changed by the story
- verify: json_path(path="$.services", matches=".*")
- semantics: an empty list permits repository-root dispatch
- verify: json_path(path="$.services", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanResult.services`

### implementation_order
- type: `list[str]`
- default: empty list
- required: false
- semantics: `repo::path` keys ordered from contract producers to consumers
- verify: json_path(path="$.implementation_order", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanResult.implementation_order`

### shared_packages
- type: `list[PlanService]`
- default: empty list
- required: false
- semantics: non-service directories changed by the story
- verify: json_path(path="$.shared_packages", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanResult.shared_packages`

### verification_setup
- type: `dict[str, Any]`
- default: empty mapping
- required: false
- semantics: QA profile and rendering capability declared by the story
- verify: json_path(path="$.verification_setup", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanResult.verification_setup`

### fixtures
- type: `list[PlanFixture]`
- default: empty list
- required: false
- semantics: typed fixture declarations extracted from verification setup or supplied directly
- verify: json_path(path="$.fixtures", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanResult.fixtures`
