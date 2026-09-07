---
type: format
slug: seed-snapshot
title: Epic seed snapshot
---
# Epic seed snapshot

The baseline metadata for one epic seed used during edit-plan validation.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [epic edit snapshot](epic-snapshot.md)

## Fields

### id
- type: string
- default: empty string
- required: false
- semantics: seed identifier
- verify: json_path(path="$.id", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
### status
- type: string
- default: empty string
- required: false
- semantics: current seed lifecycle status
- verify: json_path(path="$.status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
### summary
- type: string
- default: empty string
- required: false
- semantics: seed summary
- verify: json_path(path="$.summary", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
### surface
- type: string
- default: empty string
- required: false
- semantics: product surface named by the seed
- verify: json_path(path="$.surface", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
### legacy_surface
- type: string
- default: empty string
- required: false
- semantics: legacy surface metadata retained by the seed
- verify: json_path(path="$.legacy_surface", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
### backing
- type: string
- default: empty string
- required: false
- semantics: backing system named by the seed
- verify: json_path(path="$.backing", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
### prerequisites
- type: string
- default: empty string
- required: false
- semantics: seed prerequisites
- verify: json_path(path="$.prerequisites", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
### source_bullet
- type: string
- default: empty string
- required: false
- semantics: source bullet text
- verify: json_path(path="$.source_bullet", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
### frozen
- type: boolean
- default: false
- required: false
- semantics: whether the seed may be changed by the plan
- verify: json_path(path="$.frozen", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedSnapshot`
- detail: [seed snapshot field roles](concepts/seed-snapshot-field-roles.md)
