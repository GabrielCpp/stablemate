---
type: concept
slug: record-check-field-roles
title: Record check field roles
---
# Record check field roles

`RecordCheck` reports one deterministic validation outcome through two complementary fields.
`record_ok` is the boolean decision consumed by the flow, while `record_errors` carries the
diagnostic text that explains a failed decision. Neither field replaces the other and source
does not establish a ranking between them.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordCheck`
- rule: use `record_ok` to branch on validation success; use `record_errors` to report why validation failed
