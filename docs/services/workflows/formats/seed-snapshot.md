---
type: format
slug: seed-snapshot
title: Epic seed snapshot
---
# Epic seed snapshot

The baseline metadata for one epic seed used during edit-plan validation.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [epic edit snapshot](epic-snapshot.md)

## Fields

### id
- type: string
- default: empty string
- required: false
- semantics: seed identifier
- verify: json_path(path="$.id", equals="CASE-1234")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
### status
- type: string
- default: empty string
- required: false
- semantics: current seed lifecycle status
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
### summary
- type: string
- default: empty string
- required: false
- semantics: seed summary
- verify: json_path(path="$.summary", equals="Story built and checked.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
### surface
- type: string
- default: empty string
- required: false
- semantics: product surface named by the seed
- verify: json_path(path="$.surface", equals="example surface")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
### legacy_surface
- type: string
- default: empty string
- required: false
- semantics: legacy surface metadata retained by the seed
- verify: json_path(path="$.legacy_surface", equals="example legacy surface")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
### backing
- type: string
- default: empty string
- required: false
- semantics: backing system named by the seed
- verify: json_path(path="$.backing", equals="example backing")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
### prerequisites
- type: string
- default: empty string
- required: false
- semantics: seed prerequisites
- verify: json_path(path="$.prerequisites", equals="example prerequisites")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
### source_bullet
- type: string
- default: empty string
- required: false
- semantics: source bullet text
- verify: json_path(path="$.source_bullet", equals="example source bullet")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
### frozen
- type: boolean
- default: false
- required: false
- semantics: whether the seed may be changed by the plan
- verify: json_path(path="$.frozen", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot` @7b95d62cfa2c
- detail: [seed snapshot field roles](../concepts/seed-snapshot-field-roles.md)
