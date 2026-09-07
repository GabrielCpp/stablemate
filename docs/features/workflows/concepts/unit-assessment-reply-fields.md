---
type: concept
slug: unit-assessment-reply-fields
title: Unit assessment reply fields
---
# Unit assessment reply fields

`UnitAssessment` records both the outcome of assessing one unit and the explanation needed to
interpret that outcome. The fields are complementary rather than alternative implementations.

Use `status` for the enumerated outcome: `assessed`, `clean`, `blocked`, or `split`. The
surveyor flow routes only `split`, which requests that an oversized unit be subdivided. Use
`notes` for the assessment explanation and, when the outcome is `blocked` or `split`, the
context that explains it. Do not substitute one field for the other: a status does not carry
the rationale, and notes do not select the flow route.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitAssessment`
- rule: use `status` for the outcome and `notes` for its explanation or blocked/split context
