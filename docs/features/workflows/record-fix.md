---
type: format
slug: record-fix
title: Survey record-fix reply
---
# Survey record-fix reply

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)

The repair turn's advisory response for an invalid finding record. Validation remains the
authority after this reply.

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: repair outcome: `fixed` or `blocked`
- verify: json_path(path="$.status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix`
- detail: [record-fix field roles](concepts/record-fix-field-roles.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: repair explanation
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix`
- detail: [record-fix field roles](concepts/record-fix-field-roles.md)
