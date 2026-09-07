---
type: concept
slug: seed-change-field-roles
title: Seed change field roles
---
# Seed change field roles

`SeedChange` projects one seed mutation. Its fields are complementary parts of that projection,
not alternative implementations: `action` selects the structural operation, `id` identifies the
seed, and the remaining fields carry the resulting seed metadata, source disposition, and
rationale.

The schema declares every field directly with its own type and default. It has no legacy marker,
delegation, wrapper, or preference between fields, so no field supersedes another. Select the
field that represents the seed attribute being changed; combine fields when one change needs
multiple attributes.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- rule: select fields by the seed attribute a projected change carries; the fields are complementary and no ranking exists
