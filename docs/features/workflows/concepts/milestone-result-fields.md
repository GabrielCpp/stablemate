---
type: concept
slug: milestone-result-fields
title: Milestone result fields
---
# Milestone result fields

`MilestoneResult` declares `status` and `notes` as separate required attributes. `status` is a
`Literal["complete", "blocked"]`; `notes` is a string. The schema records no ranking or
substitution between them: consumers use `status` for the outcome and `notes` for its detail.

- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneResult`
- rule: no selection rule exists; `status` and `notes` are separate required result attributes
- detail: [milestone result field roles](milestone-result-field-roles.md)
