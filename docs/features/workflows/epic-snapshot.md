---
type: format
slug: epic-snapshot
title: Epic edit snapshot
---
# Epic edit snapshot

The immutable baseline captured before an epic edit is planned. It identifies the epic and its
document roots, hashes the epic body, and carries the seed, story, and milestone snapshots used to
reject plans based on stale or changed graph state.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [author epic edit subflow](concepts/author-epic-edit-subflow.md)

## Fields

### epic
- type: string
- default: empty string
- required: false
- semantics: selected epic identifier
- verify: json_path(path="$.epic", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [epic snapshot field roles](concepts/epic-snapshot-field-roles.md)

### epic_dir
- type: string path
- default: empty string
- required: false
- semantics: resolved directory containing the epic document
- verify: json_path(path="$.epic_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [epic snapshot field roles](concepts/epic-snapshot-field-roles.md)

### epics_dir
- type: string path
- default: empty string
- required: false
- semantics: configured root used to resolve the epic
- verify: json_path(path="$.epics_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [epic snapshot field roles](concepts/epic-snapshot-field-roles.md)

### title
- type: string
- default: empty string
- required: false
- semantics: current epic title
- verify: json_path(path="$.title", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [epic snapshot field roles](concepts/epic-snapshot-field-roles.md)

### epic_hash
- type: string
- default: empty string
- required: false
- semantics: content hash used to detect changes to the epic document
- verify: json_path(path="$.epic_hash", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [epic snapshot field roles](concepts/epic-snapshot-field-roles.md)

### seeds
- type: list of [seed snapshots](seed-snapshot.md)
- default: empty list
- required: false
- semantics: ordered seed state at snapshot time
- verify: json_path(path="$.seeds", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [epic snapshot field roles](concepts/epic-snapshot-field-roles.md)

### stories
- type: list of [story snapshots](story-snapshot.md)
- default: empty list
- required: false
- semantics: ordered story state at snapshot time
- verify: json_path(path="$.stories", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [epic snapshot field roles](concepts/epic-snapshot-field-roles.md)

### milestones
- type: list of [milestone snapshots](milestone-snapshot.md)
- default: empty list
- required: false
- semantics: milestones referencing the epic's source items
- verify: json_path(path="$.milestones", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- detail: [epic snapshot field roles](concepts/epic-snapshot-field-roles.md)
