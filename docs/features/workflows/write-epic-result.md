---
type: format
slug: write-epic-result
title: Write epic result
---
# Write epic result

The agent reply returned after writing one epic document carries its status and explanatory notes.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: agent-reported outcome of writing the epic
- verify: json_path(path="$.status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult`

### notes
- type: string
- default: empty string
- required: false
- semantics: agent notes accompanying the epic-writing outcome
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult`
