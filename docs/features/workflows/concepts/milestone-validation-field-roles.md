---
type: concept
slug: milestone-validation-field-roles
title: Milestone validation field roles
---
# Milestone validation field roles

`MilestoneValidation` declares `ok`, `milestone_path`, `reused`, and `errors` as separate
fields with independent defaults. They are complementary parts of one validation result, not
alternative implementations or replacement fields.

Read the complete result: `ok` states whether validation passed, `milestone_path` identifies the
validated milestone when one exists, `reused` records whether that milestone was reused, and
`errors` carries the validation failures. The schema does not rank these fields or designate a
successor; each is used for its distinct role.

- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneValidation`
- rule: consume all four fields as one validation result; do not select one field in place of another
