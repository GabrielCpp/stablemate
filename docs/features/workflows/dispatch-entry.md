---
type: format
slug: dispatch-entry
title: Coder dispatch entry
---
# Coder dispatch entry

- file: none — in-memory dispatch record
- config: `DispatchEntry` emitted by dispatch-list construction
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### service
- type: `str`
- default: empty string
- required: false
- semantics: complete `repo::path` dispatch identity
- verify: json_path(path="$.service", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.service`

### repo
- type: `str`
- default: empty string
- required: false
- semantics: repository containing the dispatched service
- verify: json_path(path="$.repo", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.repo`

### cwd
- type: `str`
- default: empty string
- required: false
- semantics: checkout directory used for the service
- verify: json_path(path="$.cwd", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.cwd`

### service_path
- type: `str`
- default: empty string
- required: false
- semantics: service path beneath the checkout
- verify: json_path(path="$.service_path", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.service_path`

### type
- type: `str`
- default: empty string
- required: false
- semantics: service technology key
- verify: json_path(path="$.type", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.type`

### plan_file
- type: `str`
- default: empty string
- required: false
- semantics: service plan file
- verify: json_path(path="$.plan_file", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.plan_file`

### qa_mode
- type: `str`
- default: empty string
- required: false
- semantics: QA mode selected for the service
- verify: json_path(path="$.qa_mode", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.qa_mode`

### qa_skills
- type: `list[str]`
- default: empty list
- required: false
- semantics: QA skills available to the service
- verify: json_path(path="$.qa_skills", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.qa_skills`

### verification
- type: `str`
- default: empty string
- required: false
- semantics: verification setup associated with the service
- verify: json_path(path="$.verification", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.verification`

### label
- type: `str`
- default: empty string
- required: false
- semantics: display name for the service, distinct from its dispatch identity
- verify: json_path(path="$.label", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.label`
