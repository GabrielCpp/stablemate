---
type: concept
slug: epic-split-validation-field-roles
title: Epic split validation field roles
---
# Epic split validation field roles

`workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitValidation` returns a
single validation report. Its four fields are complementary observations, not competing
implementations: `ok` carries the aggregate verdict, `milestone_path` identifies the uniquely
matched roadmap milestone, `ordered_epics` records that milestone's authored epic order, and
`errors` carries the newline-separated findings when validation fails.

The model declaration assigns each field its own type and default: `False`, `""`, an empty list,
and `""`, respectively. It records neither a deprecated field nor a preferred replacement, so no
ranking exists. Read `ok` first to determine the verdict. When it is false, read `errors` for the
findings; use `milestone_path` and `ordered_epics` to inspect the milestone evidence the verdict
was evaluated against. A complete validation report may require all four fields.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitValidation`
- rule: use `ok` for the verdict, `errors` for failed-invariant findings, and `milestone_path` with `ordered_epics` for the milestone evidence; no field replaces another
