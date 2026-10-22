---
type: format
slug: record-fix
title: Survey record-fix reply
---
# Survey record-fix reply

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix` @7db58efbfd66
- detail: [author surveyor subflow](../concepts/author-surveyor-subflow.md)

The repair turn's advisory response for an invalid finding record. Validation remains the
authority after this reply.

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: repair outcome: `fixed` or `blocked`
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix` @7db58efbfd66
- detail: [record-fix field roles](../concepts/record-fix-field-roles.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: repair explanation
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix` @7db58efbfd66
- detail: [record-fix field roles](../concepts/record-fix-field-roles.md)
