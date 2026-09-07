---
type: concept
slug: applied-epic-edit-field-roles
title: Applied epic edit field roles
---
# Applied epic edit field roles

`AppliedEpicEdit` reports the outcome of one approved epic edit. Its fields are complementary
observations, not alternate representations of the same value: `changed` records whether the
graph changed; `epic` identifies the target; `epic_dir` locates an epic that remains; `deleted`
records whether that epic was deleted; `affected_stories` lists surviving stories that need later
processing; and `removed_stories` lists stories removed by the edit.

The schema declares each field directly with an independent default and does not mark any as
legacy, delegated, or preferred. Consumers select the field that answers their specific outcome
question; no field ranks above or replaces another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::AppliedEpicEdit`
- rule: select the field that answers the outcome question; the six fields are complementary and no ranking exists
