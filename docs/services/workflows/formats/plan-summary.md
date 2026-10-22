---
type: format
slug: plan-summary
title: Coder plan summary
---
# Coder plan summary

- file: none — in-memory rendered plan summary
- config: `PlanSummary` prompt value
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanSummary` @bcd75ac6f796
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### text
- type: `str`
- default: empty string
- required: false
- semantics: human-readable plan structure, blank when no projection exists
- verify: json_path(path="$.text", equals="Applied the change.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::PlanSummary.text` @bcd75ac6f796
