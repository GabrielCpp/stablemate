---
type: concept
slug: coder-queue-epic-pick-field-roles
title: Coder queue epic pick field roles
---
# Coder queue epic pick field roles

`EpicPick` is one queue-selection result, not three alternative ways to represent it. The
selection decision comes first: read `has_epic`. When it is true, `epic` names the front queued
epic that is not set aside. When it is false, the run ends and `reason` distinguishes an empty
queue, where every epic was merged, from a queue whose remaining epics were all set aside during
this run. `epic` and `reason` do not replace each other and are not separately selected.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPick`
- rule: read `has_epic` first; use `epic` only when it is true, otherwise use `reason` to distinguish why no selectable epic remains
