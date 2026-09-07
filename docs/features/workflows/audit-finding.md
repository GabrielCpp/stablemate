---
type: format
slug: audit-finding
title: Audit finding
---
# Audit finding

One defect the story auditor is willing to fail the story over. The closed kind identifies the
audited axis, while target, issue, and repair make the finding actionable.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### id
- type: string
- default: empty string
- required: false
- semantics: stable identifier for the finding
- verify: json_path(path="$.id", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding`
- detail: [audit finding field roles](concepts/audit-finding-field-roles.md)

### kind
- type: `Literal["journey", "chrome", "transient-feedback", "grounding"]`
- default: grounding
- required: false
- semantics: audited defect axis
- verify: json_path(path="$.kind", equals="grounding")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding`
- detail: [audit finding field roles](concepts/audit-finding-field-roles.md)

### target
- type: string
- default: empty string
- required: false
- semantics: story section or line against which the defect is reported
- verify: json_path(path="$.target", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding`
- detail: [audit finding field roles](concepts/audit-finding-field-roles.md)

### issue
- type: string
- default: empty string
- required: false
- semantics: defect explanation
- verify: json_path(path="$.issue", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding`
- detail: [audit finding field roles](concepts/audit-finding-field-roles.md)

### repair
- type: string
- default: empty string
- required: false
- semantics: repair direction supplied for the defect
- verify: json_path(path="$.repair", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding`
- detail: [audit finding field roles](concepts/audit-finding-field-roles.md)
