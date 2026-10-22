---
type: concept
slug: mockup-gate-field-roles
title: Mockup gate field roles
---
# Mockup gate field roles

`MockupGate` carries one decision and the context that makes it reviewable. Its fields are
complementary, not alternative ways to represent the same result: select `required` to decide
whether authoring must include a mockup turn; select `services` to identify the
story's books; and select `evidence` to retain the source material supporting
that decision. The default of `required` is deliberately conservative when the
decision is unknown, whereas the other fields explain the result at the checkpoint and in
telemetry.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate` @69af1329fede
- rule: use each field for its distinct decision or explanatory role; none substitutes for another
