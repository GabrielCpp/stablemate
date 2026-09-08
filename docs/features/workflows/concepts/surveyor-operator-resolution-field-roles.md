---
type: concept
slug: surveyor-operator-resolution-field-roles
title: Surveyor operator resolution field roles
---
# Surveyor operator resolution field roles

`OperatorResolution` is a diagnostic report for an operator gate, not a choice among
interchangeable fields. The resolver never makes the operator's decision: it investigates the
block, writes its findings into context, and the flow parks at `Await`. `decision` remains only
to preserve the old auto-resolve reply shape and is not read. `notes` carries the current
diagnostic findings, while `tried` records the attempted and ruled-out actions so the operator
does not repeat them. No ranking exists because each field has a distinct role.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution`
- rule: read `notes` for current diagnostic findings and `tried` for ruled-out actions; retain `decision` only for the legacy reply shape and do not use it to decide the gate
- detail: [operator resolution documentation context](operator-resolution-documentation-context.md)
