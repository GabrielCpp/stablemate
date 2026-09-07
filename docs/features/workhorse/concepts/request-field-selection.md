---
type: concept
slug: request-field-selection
title: Request field selection
---
# Request field selection

`Request` uses one flat JSON record for every control verb so an older run can discard
unrecognized keys while preserving the verb it understands. Select `action` first, then supply
only the fields that refine that action: `core`, `at_boundary`, and `cli` configure a reload;
`profile` selects a profile; and `path` with `body` identifies and supplies an operator-gate
answer. `requested_at` is transport metadata added during serialization. Empty values mean the
field does not apply to that request and retain the receiving run's current choice where
applicable.

- code: `workhorse/workhorse/control.py::Request`
- rule: select fields by the request action; use each field only for the action or wire concern it represents
