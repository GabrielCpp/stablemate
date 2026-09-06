---
type: format
slug: plan-summary
title: Coder plan summary
---
# Coder plan summary

- file: none — in-memory rendered plan summary
- config: `PlanSummary` prompt value
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanSummary`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### text
- type: `str`
- default: empty string
- required: false
- semantics: human-readable plan structure, blank when no projection exists
- verify: json_path(path="$.text", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanSummary.text`
