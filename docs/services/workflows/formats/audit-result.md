---
type: format
slug: audit-result
title: Audit result
---
# Audit result

The story audit reply carries a summary status and the findings that determine whether the story
passes. An empty findings list is the pass evidence; `notes` is explanatory only.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult` @f9301e7de2f3
- detail: [author shared schemas](../concepts/author-shared-schemas.md)

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: agent-reported audit status
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult` @f9301e7de2f3
- detail: [audit result field roles](../concepts/audit-result-field-roles.md)

### findings
- type: list of [audit findings](audit-finding.md)
- default: empty list
- required: false
- semantics: defects the auditor found in the story
- verify: count(subject="findings", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult` @f9301e7de2f3
- detail: [audit result field roles](../concepts/audit-result-field-roles.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: audit summary accompanying the findings
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult` @f9301e7de2f3
- detail: [audit result field roles](../concepts/audit-result-field-roles.md)
