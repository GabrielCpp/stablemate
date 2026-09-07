---
type: format
slug: seed-change
title: Epic seed change
---
# Epic seed change

One projected seed mutation in an epic edit plan.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [epic edit plan](epic-edit-plan.md)

## Fields
### action
- type: `Literal["add", "update", "remove"]`
- default: add
- required: false
- semantics: structural operation applied to the seed
- verify: json_path(path="$.action", equals="add")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### id
- type: string
- default: empty string
- required: false
- semantics: seed identifier
- verify: json_path(path="$.id", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### status
- type: string
- default: researched
- required: false
- semantics: resulting seed status
- verify: json_path(path="$.status", equals="researched")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### summary
- type: string
- default: empty string
- required: false
- semantics: resulting seed summary
- verify: json_path(path="$.summary", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### surface
- type: string
- default: empty string
- required: false
- semantics: resulting product surface
- verify: json_path(path="$.surface", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### legacy_surface
- type: string
- default: empty string
- required: false
- semantics: resulting legacy surface metadata
- verify: json_path(path="$.legacy_surface", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### backing
- type: string
- default: empty string
- required: false
- semantics: resulting backing system
- verify: json_path(path="$.backing", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### prerequisites
- type: string
- default: empty string
- required: false
- semantics: resulting prerequisites
- verify: json_path(path="$.prerequisites", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### source_bullet
- type: string
- default: empty string
- required: false
- semantics: source bullet text
- verify: json_path(path="$.source_bullet", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### disposition
- type: `Literal["retain", "drop"]`
- default: retain
- required: false
- semantics: whether the source item remains in the resulting graph
- verify: json_path(path="$.disposition", equals="retain")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
### reason
- type: string
- default: empty string
- required: false
- semantics: rationale for the projected seed change
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::SeedChange`
- detail: [seed change field roles](concepts/seed-change-field-roles.md)
