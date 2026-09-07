---
type: concept
slug: coder-queue-epic-branch-field-roles
title: Coder queue epic branch field roles
---
# Coder queue epic branch field roles

`EpicBranch` records one run's epic branch state. `working_epic` identifies the epic the branch
belongs to; `epic_branch` carries that epic's `feat/<epic>` branch name, including `feat/` when
the epic is blank. The fields are complementary parts of one result, not alternative interfaces,
and neither replaces or ranks above the other.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBranch`
- rule: read `working_epic` to identify the epic and `epic_branch` to identify its branch; no field is preferred or deprecated because both describe the same branch state
