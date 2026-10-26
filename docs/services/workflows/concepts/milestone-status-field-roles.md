---
type: concept
slug: milestone-status-field-roles
title: Milestone status field roles
---
# Milestone status field roles

`MilestoneStatus` reports the durable result of Author's final milestone lifecycle transition.
Its two string fields have complementary roles: `path` identifies the milestone document that
was transitioned, while `status` carries the lifecycle status written to that document.

Neither field supersedes the other or is a substitute for it. Consumers that need to identify
the transitioned milestone use `path`; consumers that need the resulting lifecycle state use
`status`. The schema declares both fields with an empty-string default, so the source records
no further ranking or selection rule between them.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MilestoneStatus` @c0c7fb10e846
- rule: use `path` for the transitioned milestone's identity and `status` for its recorded lifecycle state; neither field is preferred over the other
