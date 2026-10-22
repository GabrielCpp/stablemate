---
type: concept
slug: milestone-result-field-roles
title: Milestone result field roles
---
# Milestone result field roles

`MilestoneResult` has two required, complementary result fields: `status` is limited to
`"complete"` or `"blocked"`, while `notes` is a string. The schema gives neither field a
substitute or a ranking, so callers use the outcome field for routing and the detail field for
the associated message rather than choosing one implementation over the other.

- rule: use `status` for the complete-versus-blocked outcome and `notes` for its detail; neither field supersedes the other
