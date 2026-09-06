---
type: format
slug: pr-gate
title: Pull request gate result
---
# Pull request gate result

- file: none — an in-memory result returned between coder workflow nodes
- config: none — its values are produced from the PR-opening node inputs
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::PrGate`
- detail: [coder main PR boundary](concepts/coder-main-pr-boundary.md)

The result says whether the epic pull request requires CI gating and carries the exact epic and
base branches used by later CI and merge nodes.

## Fields

### should_gate

- type: `bool`
- default: `false`
- required: false
- semantics: whether the workflow must continue through pull-request CI and merge gates
- verify: json_path(path="$.should_gate", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::PrGate.should_gate`

### ci_epic

- type: `str`
- default: empty string
- required: false
- semantics: the epic branch or identifier carried to the CI and merge chain
- verify: json_path(path="$.ci_epic", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::PrGate.ci_epic`

### ci_base

- type: `str`
- default: empty string
- required: false
- semantics: the base branch against which the epic pull request is gated and merged
- verify: json_path(path="$.ci_base", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::PrGate.ci_base`
