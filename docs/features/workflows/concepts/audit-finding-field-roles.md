---
type: concept
slug: audit-finding-field-roles
title: Audit finding field roles
---
# Audit finding field roles

`AuditFinding` carries five complementary attributes for one actionable audit defect. They are not
alternative implementations and none substitutes for another: `id` identifies the finding,
`kind` classifies its audited axis, `target` identifies the story location, `issue` explains the
defect, and `repair` supplies the repair direction.

The schema declares all five fields on the same record. Its class documentation further specifies
that `kind` is closed to the four audit axes and that `target` must identify the section or line
against which the defect is reported. The source establishes no ranking, deprecation, or
replacement relationship among the fields.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditFinding`
- rule: use every field for its named role when reading or producing an audit finding; do not choose one as an alternative to another
