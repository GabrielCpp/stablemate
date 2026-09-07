---
type: concept
slug: expansion-result-field-roles
title: Expansion result field roles
---
# Expansion result field roles

`Expansion` reports the result of `expand_inventory` whether it materialized the inventory or
used an already-frozen list. Its four fields are complementary observations, not alternative
implementations or aliases: read `expand_ok` to decide whether the result is usable,
`expand_errors` for diagnostic text, `unit_count` for the resulting inventory size, and
`inventory_note` for whether the inventory was reused or expanded.

The schema declares no preference or deprecation among these fields. Callers needing more than
one aspect of the result use the corresponding fields together rather than selecting a winner.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::Expansion`
- rule: use each field for its named result aspect; no field ranks above or replaces another
