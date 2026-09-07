---
type: concept
slug: write-story-result-field-roles
title: Write story result field roles
---
# Write story result field roles

`WriteStoryResult` carries `status` and `notes` as independent optional string fields. The schema
does not deprecate either field or designate one as a replacement for the other. A result records
the agent-reported story-writing outcome in `status` and the accompanying explanatory notes in
`notes`; both apply to the same response.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::WriteStoryResult`
- rule: read `status` for the story-writing outcome and `notes` for its explanation; neither field replaces the other
