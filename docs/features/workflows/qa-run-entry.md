---
type: format
slug: qa-run-entry
title: Coder QA run entry
---
# Coder QA run entry

- file: none — in-memory QA brief
- config: `QaRunEntry` derived from a dispatch entry
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### service
- type: `str`
- default: empty string
- required: false
- semantics: service dispatch identity
- verify: json_path(path="$.service", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry.service`

### label
- type: `str`
- default: empty string
- required: false
- semantics: service display label
- verify: json_path(path="$.label", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry.label`

### qa_mode
- type: `str`
- default: empty string
- required: false
- semantics: QA mode selected for this service
- verify: json_path(path="$.qa_mode", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry.qa_mode`

### qa_skill
- type: `str`
- default: empty string
- required: false
- semantics: primary QA skill
- verify: json_path(path="$.qa_skill", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry.qa_skill`

### qa_skills
- type: `list[str]`
- default: empty list
- required: false
- semantics: all QA skills retained for the service
- verify: json_path(path="$.qa_skills", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry.qa_skills`
