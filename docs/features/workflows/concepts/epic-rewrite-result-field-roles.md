---
type: concept
slug: epic-rewrite-result-field-roles
title: Epic rewrite result field roles
---
# Epic rewrite result field roles

`EpicRewriteResult` declares `status` as a `"complete"` or `"blocked"` outcome with a
`"blocked"` default, while its independent `notes` string defaults to empty. The fields are
complementary parts of one rewrite reply: `status` supplies the result used to determine the
outcome, and `notes` supplies any accompanying agent context. Neither replaces the other, and
the source declares no ranking between them.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicRewriteResult`
- rule: use `status` to determine the rewrite outcome and `notes` to read accompanying agent context; no selection rule applies because the fields serve distinct roles in the same reply
