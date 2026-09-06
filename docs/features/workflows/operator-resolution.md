---
type: format
slug: operator-resolution
title: Operator resolution
---
# Operator resolution

The resolver reply records that an unresolved epic-split decision was escalated and what diagnostic
steps were attempted before the workflow awaits an operator.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution`
- detail: [author epic split subflow](concepts/author-epic-split-subflow.md)

## Fields

### decision
- type: literal `escalated`
- required: true
- semantics: confirms the resolver did not make an unsupported product or scope decision
- verify: json_path(path="$.decision", equals="escalated")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution`

### notes
- type: string
- required: true
- semantics: diagnostic explanation presented with the operator gate
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution`

### tried
- type: list of strings
- default: empty list
- required: true
- semantics: diagnostic actions completed before escalation
- verify: json_path(path="$.tried", equals=[])
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution`
