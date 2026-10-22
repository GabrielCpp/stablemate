---
type: format
slug: write-epic-result
title: Write epic result
---
# Write epic result

The agent reply returned after writing one epic document carries its status and explanatory notes.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult` @0c2f7d227faf
- detail: [author shared schemas](../concepts/author-shared-schemas.md)

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: agent-reported outcome of writing the epic
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult` @0c2f7d227faf
- detail: [write epic result field roles](../concepts/write-epic-result-field-roles.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: agent notes accompanying the epic-writing outcome
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult` @0c2f7d227faf
- detail: [write epic result field roles](../concepts/write-epic-result-field-roles.md)
