---
type: concept
slug: seed-snapshot-field-roles
title: Seed snapshot field roles
---
# Seed snapshot field roles

`SeedSnapshot` captures the seed baseline before an epic edit is planned. Its fields are
complementary attributes, not alternate implementations: `id` identifies the seed; `status`,
`summary`, `surface`, `legacy_surface`, `backing`, `prerequisites`, and `source_bullet` preserve
its listed metadata; and `frozen` records whether the seed is protected from removal.

`snapshot_epic` reads each metadata value from the seed record into its corresponding field, and
the edit-plan projection and validation compare each one independently. The schema declares no
legacy marker, delegation, wrapper, or preference between these fields, so no field supersedes
another. Select the field for the seed attribute required by the baseline.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- rule: select the field for the seed attribute required by the pre-edit baseline; the nine fields are complementary and no ranking exists
