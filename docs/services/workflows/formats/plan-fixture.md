---
type: format
slug: plan-fixture
title: Coder plan fixture
---
# Coder plan fixture

- file: none — in-memory nested QA fixture declaration
- config: `PlanFixture` entries returned by the plan result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanFixture` @5aa622da8aea
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### name
- type: `str`
- default: empty string
- required: false
- semantics: fixture key resolved from the repository QA declaration
- verify: json_path(path="$.name", equals="acme")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanFixture.name` @5aa622da8aea

### provides
- type: `str`
- default: empty string
- required: false
- semantics: state guaranteed by the fixture and available to a QA scenario
- verify: json_path(path="$.provides", equals="example provides")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanFixture.provides` @5aa622da8aea
