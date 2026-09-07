---
type: concept
slug: mockup-gate-field-roles
title: Mockup gate field roles
---
# Mockup gate field roles

`MockupGate` carries one decision and the context that makes it reviewable. Its fields are
complementary, not alternative ways to represent the same result: select `required` to decide
whether authoring must include a mockup turn; select `layers` and `services` to identify the
union of covered-seed context; and select `evidence` to retain the source material supporting
that decision. The default of `required` is deliberately conservative when story or seed
classification is missing, whereas the other fields explain the result at the checkpoint and in
telemetry.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate`
- rule: use each field for its distinct decision or explanatory role; none substitutes for another
