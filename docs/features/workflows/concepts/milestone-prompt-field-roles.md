---
type: concept
slug: milestone-prompt-field-roles
title: Milestone prompt field roles
---
# Milestone prompt field roles

The fields grounded in `Milestone.start` are complementary, not alternative implementations. The
method passes the approved roadmap to the agent as `roadmap`; it uses a `blocked` status to route
the turn to `Await` and supplies `notes` as that operator-facing message. A non-blocked result is
validated before completion. `MilestoneResult` declares `status` and `notes`; the roadmap remains
the supplied input rather than a result attribute.

- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.start`
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneResult`
- rule: use `roadmap` to identify the approved source item, `status` to select blocked versus validation routing, and `notes` as the blocked-turn message; no field replaces or ranks another
