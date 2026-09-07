---
type: concept
slug: plan-result-fields
title: Plan result fields
---
# Plan result fields

`PlanResult` records the survey planner's response in two complementary fields. `status` names
the outcome: `complete` permits the plan to proceed, while `blocked` routes it to the operator
gate. `notes` carries the enumeration rules the planner wrote. The schema declares neither field
as a substitute for the other or as preferred; consumers use `status` to select the outcome path
and `notes` to read the planner's explanation.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PlanResult`
- rule: use `status` for the `complete` or `blocked` outcome and `notes` for the planner's enumeration rules; no ranking exists because the fields serve different purposes
