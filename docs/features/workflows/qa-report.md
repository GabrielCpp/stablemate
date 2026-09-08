---
type: format
slug: qa-report
title: QA report result
---
# QA report result

The verdict `report-qa-dev.md` and `report-qa-dev-pass.md` report on writing the QA findings or pass back to the development tracker — whether the comment file was created successfully.

- file: none — agent reply and checkpoint value
- config: `QaReport` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaReport`
- detail: [coder QA schema contracts](concepts/coder-qa-schema-contracts.md)

## Fields

### status

- type: literal `reported` or `blocked`
- required: true
- semantics: `reported` once the comment file exists
- verify: json_path(path="$.status", equals="reported")
- semantics: `blocked` when the evidence cannot be read or the output path cannot be written
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaReport.status`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: the output path and what the comment says
- verify: json_path(path="$.notes", matches=".*")
- semantics: on `blocked`, what was missing
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaReport.notes`

