---
type: format
slug: operator-gate
title: Operator gate result
---
# Operator gate result

The result passed from a coder escalation helper to `Await`. `body` is already a complete context
file, including its leading status line, and `number` records the escalation ordinal for logging
and continuation.

- file: none — in-memory workflow result
- config: block context and story paths supplied to the escalation composer
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorGate`
- detail: [Coder escalation composition](concepts/coder-shared-escalation.md)

## Fields

### body
- type: `str`
- default: empty string
- required: false
- semantics: newline-terminated operator context containing `STATUS: AWAITING_OPERATOR` and the complete escalation question
- verify: json_path(path="$.body", matches="^STATUS: AWAITING_OPERATOR")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorGate.body`

### number
- type: `int`
- default: `0`
- required: false
- semantics: escalation ordinal carried for caller logging and gate context
- verify: json_path(path="$.number", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::OperatorGate.number`
