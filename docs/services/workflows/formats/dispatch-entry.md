---
type: format
slug: dispatch-entry
title: Coder dispatch entry
---
# Coder dispatch entry

- file: none — in-memory dispatch record
- config: `DispatchEntry` emitted by dispatch-list construction
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry` @bcd75ac6f796
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### service
- type: `str`
- default: empty string
- required: false
- semantics: complete `repo::path` dispatch identity
- verify: json_path(path="$.service", equals="example service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.service` @bcd75ac6f796

### repo
- type: `str`
- default: empty string
- required: false
- semantics: repository containing the dispatched service
- verify: json_path(path="$.repo", equals="api-service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.repo` @bcd75ac6f796

### cwd
- type: `str`
- default: empty string
- required: false
- semantics: checkout directory used for the service
- verify: json_path(path="$.cwd", equals="example cwd")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.cwd` @bcd75ac6f796

### service_path
- type: `str`
- default: empty string
- required: false
- semantics: service path beneath the checkout
- verify: json_path(path="$.service_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.service_path` @bcd75ac6f796

### type
- type: `str`
- default: empty string
- required: false
- semantics: service technology key
- verify: json_path(path="$.type", equals="example type")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.type` @bcd75ac6f796

### plan_file
- type: `str`
- default: empty string
- required: false
- semantics: service plan file
- verify: json_path(path="$.plan_file", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.plan_file` @bcd75ac6f796

### label
- type: `str`
- default: empty string
- required: false
- semantics: display name for the service, distinct from its dispatch identity
- verify: json_path(path="$.label", equals="acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::DispatchEntry.label` @bcd75ac6f796
