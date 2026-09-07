---
type: concept
slug: mark-result-field-roles
title: Mark result field roles
---
# Mark result field roles

`MarkResult` in `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult`
is the return shape for `mark_unit`. Its three fields describe separate aspects of that
operation, not alternative implementations or replacements. The source declares `marked` as a
boolean defaulting to `false`, while `unit_status` and `mark_note` are independent strings
defaulting to empty values; it records no deprecation, delegation, or preferred field.

Read `marked` to determine whether the matching inventory entry was written. Read
`unit_status` to obtain the status read from or assigned to the finding record. Read `mark_note`
for diagnostic or outcome text. A caller may need more than one of these fields: no source-level
ranking exists among them.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::MarkResult`
- rule: select each field for its distinct result role; combine fields when both write outcome,
  resulting status, and diagnostic context are needed
