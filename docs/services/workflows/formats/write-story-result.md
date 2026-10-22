---
type: format
slug: write-story-result
title: Write story result
---
# Write story result

The agent response describing a story-writing turn. Its status controls the next authoring branch;
notes carry the turn's explanation to validation, rework, or an operator gate.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteStoryResult` @69af1329fede
- detail: [author epic edit subflow](../concepts/author-epic-edit-subflow.md)

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: outcome used to route story writing
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteStoryResult` @69af1329fede
- detail: [write story result field roles](../concepts/write-story-result-field-roles.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: writer explanation passed to the next branch or gate
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteStoryResult` @69af1329fede
- detail: [write story result field roles](../concepts/write-story-result-field-roles.md)
