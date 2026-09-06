---
type: format
slug: audit-result
title: Audit result
---
# Audit result

The story audit reply carries a summary status and the findings that determine whether the story
passes. An empty findings list is the pass evidence; `notes` is explanatory only.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: agent-reported audit status
- verify: json_path(path="$.status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult`

### findings
- type: list of [audit findings](audit-finding.md)
- default: empty list
- required: false
- semantics: defects the auditor found in the story
- verify: json_path(path="$.findings", equals=[])
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult`

### notes
- type: string
- default: empty string
- required: false
- semantics: audit summary accompanying the findings
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult`
