---
type: concept
slug: unit-pick-fields
title: Unit pick fields
---
# Unit pick fields

`UnitPick` is the result of selecting the next pending inventory unit. Its fields are one
record, not competing implementations: `has_unit` states whether a selection was made;
`unit_id`, `unit_path`, `unit_kind`, and `record_path` describe that selection; and `reason`,
`progress`, and `kinds` describe an empty selection or its inventory snapshot.

The schema declares these attributes together and contains no deprecation or preference between
them. Consumers read the field whose documented meaning answers the question at hand; no field
substitutes for another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::UnitPick`
- rule: select the UnitPick field by the information required; the schema records no ranking or replacement among its fields
