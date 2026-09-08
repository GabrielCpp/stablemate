---
type: concept
slug: push-outcome-field-roles
title: Push outcome field roles
---
# Push outcome field roles

`PushOutcome` communicates one push result through both fields. `status` classifies the outcome:
`pushed` confirms the remote head advanced, `unavailable` means a push could not be attempted, and
`failed` records an attempted push that did not land or could not be verified. `notes` carries the
reason and branch or checkout context needed to interpret that classification. The source
[`PushOutcome` docstring](../../../../workflows/src/workhorse_workflows/coder/shared/schemas/ci.py)
defines `unavailable` as tolerated and `failed` as an attempted but unverified push.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::PushOutcome`
- rule: read `status` to select the push outcome and `notes` for its explanation and context; neither field replaces the other
