---
type: concept
slug: epic-edit-plan-field-roles
title: Epic edit plan field roles
---
# Epic edit plan field roles

`EpicEditPlan` is a complete replacement projection, so its nine fields carry distinct parts of
one proposed epic edit rather than alternate implementations. `status` controls validation
readiness; `epic` names the target; `delete_epic` records the structural deletion decision;
`summary` and `notes` carry planner context; `journey_changes`, `seed_changes`, and
`story_changes` describe the planned changes; and `affected_stories` preserves the later prose or
coverage work order.

The schema declares each field directly with its own type and default. It contains no legacy
marker, delegation, wrapper, or preference between them, so no field supersedes another. Readers
select the field that answers the part of the replacement plan they need.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- rule: select the field for the needed part of the replacement plan; the nine fields are complementary and no ranking exists
