---
type: format
slug: survey-operator-resolution
title: Survey operator resolution reply
---
# Survey operator resolution reply

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution` @59f51b5b79f1
- detail: [author surveyor subflow](../concepts/author-surveyor-subflow.md)

The diagnostic resolver's report before the surveyor parks at the operator gate. The resolver
investigates but does not decide for the operator.

## Fields

### decision
- type: string
- default: empty string
- required: false
- semantics: retained decision field from the resolver reply
- verify: json_path(path="$.decision", equals="example decision")
- semantics: not used to decide the gate
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution` @59f51b5b79f1
- detail: [surveyor operator resolution field roles](../concepts/surveyor-operator-resolution-field-roles.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: diagnostic findings written into the operator context
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution` @59f51b5b79f1
- detail: [surveyor operator resolution field roles](../concepts/surveyor-operator-resolution-field-roles.md)

### tried
- type: list of strings
- default: empty list
- required: false
- semantics: actions attempted and ruled out before escalation
- verify: count(subject="tried", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution` @59f51b5b79f1
- detail: [surveyor operator resolution field roles](../concepts/surveyor-operator-resolution-field-roles.md)
