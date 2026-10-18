---
type: format
slug: gate-outcome
title: Coder gate outcome
---
# Coder gate outcome

- file: none — in-memory gate execution result
- config: `GateOutcome` development gate result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateOutcome` @5aa622da8aea
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### gate
- type: `str`
- default: empty string
- required: false
- semantics: declared gate identity
- verify: json_path(path="$.gate", equals="example gate")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateOutcome.gate` @5aa622da8aea

### status
- type: literal `clean`, `dirty`, or `skipped`
- default: `skipped`
- required: false
- semantics: gate result, with skipped meaning no adopted command exists
- verify: json_path(path="$.status", matches="clean|dirty|skipped")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateOutcome.status` @5aa622da8aea

### command
- type: `str`
- default: empty string
- required: false
- semantics: adopted command that ran or would have run
- verify: json_path(path="$.command", equals="make test")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateOutcome.command` @5aa622da8aea

### output
- type: `str`
- default: empty string
- required: false
- semantics: captured gate output
- verify: json_path(path="$.output", equals="example output")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateOutcome.output` @5aa622da8aea

### reason
- type: `str`
- default: empty string
- required: false
- semantics: skip or failure explanation
- verify: json_path(path="$.reason", equals="The slice works without it.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateOutcome.reason` @5aa622da8aea
