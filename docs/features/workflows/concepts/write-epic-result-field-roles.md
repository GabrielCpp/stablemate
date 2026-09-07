---
type: concept
slug: write-epic-result-field-roles
title: Write epic result field roles
---
# Write epic result field roles

`WriteEpicResult` carries `status` and `notes` as independent optional string fields. The schema
does not deprecate either field or designate one as a replacement for the other. A result records
the agent-reported epic-writing outcome in `status` and the accompanying explanatory notes in
`notes`; both apply to the same response.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteEpicResult`
- rule: read `status` for the epic-writing outcome and `notes` for its explanation; neither field replaces the other
