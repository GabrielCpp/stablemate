---
type: concept
slug: operator-resolution-field-roles
title: Operator resolution field roles
---
# Operator resolution field roles

`workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution` declares
three fields that form one operator-gate diagnostic report, not alternative implementations.
`decision` records the fixed escalation outcome, `notes` gives the diagnostic explanation shown at
the gate, and `tried` records diagnostic actions completed before escalation.

No ranking exists among these fields: a consumer uses each field for its named role, and none is a
substitute for another. The source model requires `decision` and `notes`, while `tried` defaults to
an empty list when no diagnostic actions have been recorded.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution`
- rule: read `decision` for the escalation outcome, `notes` for its explanation, and `tried` for completed diagnostic actions; do not substitute or rank fields
