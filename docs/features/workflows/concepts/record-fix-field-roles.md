---
type: concept
slug: record-fix-field-roles
title: Record-fix field roles
---
# Record-fix field roles

`RecordFix` keeps the repair outcome and its explanation in separate optional fields. `status`
is `fixed` or `blocked`; `notes` explains the repair. The fields are complementary rather than
alternatives: the surveyor revalidates the record after either outcome, so neither field decides
whether the record is valid.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::RecordFix`
- rule: use `status` for the `fixed` or `blocked` repair outcome and `notes` for its explanation; no ranking exists because the fields serve different purposes
