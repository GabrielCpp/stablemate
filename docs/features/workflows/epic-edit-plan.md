---
type: format
slug: epic-edit-plan
title: Epic edit plan
---
# Epic edit plan

A complete replacement projection for one epic edit. Validation consumes its status, target epic,
structural deletion decision, journey changes, seed and story changes, affected-story order, and
planner notes before any graph mutation occurs.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [author epic edit subflow](concepts/author-epic-edit-subflow.md)

## Fields

### status
- type: `Literal["complete", "blocked"]`
- default: blocked
- required: false
- semantics: whether the plan is ready for validation or is blocked
- verify: json_path(path="$.status", equals="complete")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)

### epic
- type: string
- default: empty string
- required: false
- semantics: epic the replacement plan addresses
- verify: json_path(path="$.epic", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)

### delete_epic
- type: boolean
- default: false
- required: false
- semantics: whether the resulting empty seed and story sets delete the epic
- verify: json_path(path="$.delete_epic", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)

### summary
- type: string
- default: empty string
- required: false
- semantics: planner summary of the replacement
- verify: json_path(path="$.summary", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)

### journey_changes
- type: list of strings
- default: empty list
- required: false
- semantics: user-journey changes that the epic rewrite must reflect
- verify: count(subject="journey_changes", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)

### seed_changes
- type: list of [seed changes](seed-change.md)
- default: empty list
- required: false
- semantics: ordered seed additions, updates, and removals
- verify: count(subject="seed_changes", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)

### story_changes
- type: list of [story changes](story-change.md)
- default: empty list
- required: false
- semantics: ordered story additions, updates, and removals
- verify: count(subject="story_changes", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)

### affected_stories
- type: list of strings
- default: empty list
- required: false
- semantics: story slugs requiring prose or coverage work after application
- verify: count(subject="affected_stories", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: planner notes passed to validation or review
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicEditPlan`
- detail: [epic edit plan field roles](concepts/epic-edit-plan-field-roles.md)
