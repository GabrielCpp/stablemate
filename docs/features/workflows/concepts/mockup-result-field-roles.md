---
type: concept
slug: mockup-result-field-roles
title: Mockup result field roles
---
# Mockup result field roles

`MockupResult` carries the outcome of a surface-sketch request for a UI story. Its fields are
complementary rather than alternative representations: `status` records the agent-reported
outcome, `surface` identifies the product surface, `mockup` holds the returned sketch, and
`notes` carries accompanying design context.

The schema declares the four fields on the same result and establishes no ranking, deprecation,
or replacement relationship among them. Consumers use each field for its named role; none is a
substitute for another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult`
- rule: use each field for its distinct outcome, surface, sketch, or accompanying-context role; do not choose one as an alternative to another
