---
type: concept
slug: survey-split-result-field-roles
title: Survey split result field roles
---
# Survey split result field roles

`SplitResult` carries all three fields; they are complementary observations of one split attempt,
not alternatives. `split_unit` returns `split_errors` on each rejected or unreadable input and
leaves `split_ok` and `children_count` at their defaults. Once it replaces a folder with eligible
immediate children, it returns `split_ok=True` and the number inserted as `children_count`.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::SplitResult`
- rule: read `split_errors` to explain a failed split; when it is empty, use `split_ok` to determine success and `children_count` to report how many immediate children replaced the folder
