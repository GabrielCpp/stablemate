---
type: format
slug: dispatch-entry
title: Coder dispatch entry
---
# Coder dispatch entry

- file: none — in-memory dispatch record
- config: `DispatchEntry` emitted by dispatch-list construction
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry` @5aa622da8aea
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### service
- type: `str`
- default: empty string
- required: false
- semantics: complete `repo::path` dispatch identity
- verify: json_path(path="$.service", equals="example service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.service` @5aa622da8aea

### repo
- type: `str`
- default: empty string
- required: false
- semantics: repository containing the dispatched service
- verify: json_path(path="$.repo", equals="api-service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.repo` @5aa622da8aea

### cwd
- type: `str`
- default: empty string
- required: false
- semantics: checkout directory used for the service
- verify: json_path(path="$.cwd", equals="example cwd")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.cwd` @5aa622da8aea

### service_path
- type: `str`
- default: empty string
- required: false
- semantics: service path beneath the checkout
- verify: json_path(path="$.service_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.service_path` @5aa622da8aea

### type
- type: `str`
- default: empty string
- required: false
- semantics: service technology key
- verify: json_path(path="$.type", equals="example type")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.type` @5aa622da8aea

### plan_file
- type: `str`
- default: empty string
- required: false
- semantics: service plan file
- verify: json_path(path="$.plan_file", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.plan_file` @5aa622da8aea

### qa_mode
- type: `str`
- default: empty string
- required: false
- semantics: QA mode selected for the service
- verify: json_path(path="$.qa_mode", equals="auto")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.qa_mode` @5aa622da8aea

### qa_skills
- type: `list[str]`
- default: empty list
- required: false
- semantics: QA skills available to the service
- verify: json_path(path="$.qa_skills", matches="^\[.*\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.qa_skills` @5aa622da8aea

### verification
- type: `str`
- default: empty string
- required: false
- semantics: verification setup associated with the service
- verify: json_path(path="$.verification", equals="example verification")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.verification` @5aa622da8aea

### label
- type: `str`
- default: empty string
- required: false
- semantics: display name for the service, distinct from its dispatch identity
- verify: json_path(path="$.label", equals="acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.label` @5aa622da8aea
