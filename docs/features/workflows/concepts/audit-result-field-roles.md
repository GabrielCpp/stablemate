---
type: concept
slug: audit-result-field-roles
title: Audit result field roles
---
# Audit result field roles

`AuditResult` carries complementary fields rather than alternative representations of its audit
outcome. `findings` is the verdict: an empty list is a pass by construction. `status` is
agent-reported free-text status, and `notes` is an explanatory summary rather than a verdict.

The schema assigns all three fields to the same reply record, but neither its declarations nor its
class documentation establishes a preference, deprecation, or replacement relationship among
them. A reader chooses the field for the needed role and must not substitute `status` or `notes`
for `findings` when determining whether an audit passed.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuditResult`
- rule: use `findings` to determine the audit verdict, `status` for agent-reported status, and `notes` for explanatory summary; none substitutes for another
