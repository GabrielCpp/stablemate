---
type: format
slug: qa-run-entry
title: Coder QA run entry
---
# Coder QA run entry

- file: none — in-memory QA brief
- config: `QaRunEntry` derived from a dispatch entry
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry` @bcd75ac6f796
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### service
- type: `str`
- default: empty string
- required: false
- semantics: service dispatch identity
- verify: json_path(path="$.service", equals="example service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry.service` @bcd75ac6f796

### label
- type: `str`
- default: empty string
- required: false
- semantics: service display label
- verify: json_path(path="$.label", equals="acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry.label` @bcd75ac6f796

### type
- type: `str`
- default: empty string
- required: false
- semantics: service type, the second tag of the QA skill lookup
- verify: json_path(path="$.type", equals="go")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::QaRunEntry.type` @bcd75ac6f796
