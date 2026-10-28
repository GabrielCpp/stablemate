---
type: format
slug: milestone-status
title: Milestone status
---
# Milestone status

The final milestone transition result identifies the milestone file and the lifecycle status written
to it.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MilestoneStatus` @b91d7be769de
- detail: [author shared schemas](../concepts/author-shared-schemas.md)

## Fields

### path
- type: string path
- default: empty string
- required: false
- semantics: milestone document whose lifecycle was transitioned
- verify: json_path(path="$.path", equals="docs/milestones/acme-launch/milestone.md")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MilestoneStatus` @b91d7be769de
- detail: [milestone status field roles](../concepts/milestone-status-field-roles.md)

### status
- type: string
- default: empty string
- required: false
- semantics: lifecycle status recorded on the milestone
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MilestoneStatus` @b91d7be769de
- detail: [milestone status field roles](../concepts/milestone-status-field-roles.md)
