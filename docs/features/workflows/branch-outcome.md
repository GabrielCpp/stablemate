---
type: format
slug: branch-outcome
title: Coder branch outcome
---
# Coder branch outcome

- file: none — in-memory branch operation result
- config: `BranchOutcome` branch dispatch result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::BranchOutcome`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### branched
- type: `list[str]`
- default: empty list
- required: false
- semantics: repositories moved onto the requested story branch
- verify: json_path(path="$.branched", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::BranchOutcome.branched`

### already_on_branch
- type: `list[str]`
- default: empty list
- required: false
- semantics: repositories already on the requested branch and left unchanged
- verify: json_path(path="$.already_on_branch", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::BranchOutcome.already_on_branch`
