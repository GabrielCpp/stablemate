---
type: format
slug: operator-answer
title: Coder operator answer
---
# Coder operator answer

- file: none — in-memory operator context result
- config: `OperatorAnswer` consumed operator context
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorAnswer` @5aa622da8aea
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### answered
- type: `bool`
- default: `false`
- required: false
- semantics: whether an operator context supplied an answer
- verify: json_path(path="$.answered", matches="true|false")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorAnswer.answered` @5aa622da8aea

### scope
- type: literal `story` or `epic`
- default: `story`
- required: false
- semantics: operator answer scope
- verify: json_path(path="$.scope", matches="story|epic")
- semantics: only an exact `epic` marker is epic scope
- verify: json_path(path="$.scope", equals="epic")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorAnswer.scope` @5aa622da8aea

### content
- type: `str`
- default: empty string
- required: false
- semantics: original operator context content
- verify: json_path(path="$.content", equals="Please recheck the login flow.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorAnswer.content` @5aa622da8aea
