---
type: format
slug: coder-operator-resolution
title: Coder operator resolution result
---
# Coder operator resolution result

The resolver's structured response used by coder escalation. `answered` decisions continue from
existing written authority; `escalated` decisions carry investigation evidence for a human.

- file: none — in-memory workflow result
- config: the resolver prompt's structured response
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorResolution`
- detail: [Coder escalation composition](concepts/coder-shared-escalation.md)

## Fields

### decision
- type: literal `answered` or `escalated`
- required: true
- semantics: whether the resolver found written authority or must hand the question to an operator
- verify: json_path(path="$.decision", matches="answered|escalated")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorResolution.decision`

### summary
- type: `str`
- default: empty string
- required: false
- semantics: one-line decision or blocker presented by the escalation
- verify: json_path(path="$.summary", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorResolution.summary`

### grounded
- type: list of strings
- default: empty list
- required: false
- semantics: written sources and quoted rules supporting an answered decision
- verify: json_path(path="$.grounded", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorResolution.grounded`

### record
- type: `str`
- default: empty string
- required: false
- semantics: decision-record slug written or cited for the resolution
- verify: json_path(path="$.record", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorResolution.record`

### tried
- type: list of strings
- default: empty list
- required: false
- semantics: concrete investigations and ruled-out hypotheses published verbatim in a later operator gate
- verify: json_path(path="$.tried", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorResolution.tried`
