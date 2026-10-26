---
type: format
slug: milestone-snapshot
title: Epic milestone snapshot
---
# Epic milestone snapshot

The milestone references captured alongside an epic so source-item ownership can be reconciled.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::MilestoneSnapshot` @f582abc9a049
- detail: [epic edit snapshot](epic-snapshot.md)

## Fields
### name
- type: string
- default: empty string
- required: false
- semantics: milestone identifier
- verify: json_path(path="$.name", equals="acme")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::MilestoneSnapshot` @f582abc9a049
- detail: [milestone snapshot field roles](../concepts/milestone-snapshot-field-roles.md)
### source_items
- type: list of strings
- default: empty list
- required: false
- semantics: source items owned by the milestone
- verify: json_path(path="$.source_items", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::MilestoneSnapshot` @f582abc9a049
- detail: [milestone snapshot field roles](../concepts/milestone-snapshot-field-roles.md)
### epics
- type: list of strings
- default: empty list
- required: false
- semantics: epics registered under the milestone
- verify: json_path(path="$.epics", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::MilestoneSnapshot` @f582abc9a049
- detail: [milestone snapshot field roles](../concepts/milestone-snapshot-field-roles.md)
