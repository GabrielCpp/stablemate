---
type: concept
slug: coder-queue-worktree-settled-field-roles
title: Coder queue worktree settled field roles
---
# Coder queue worktree settled field roles

`WorktreeSettled` reports one worktree-settlement decision through complementary fields, not
alternative representations. The schema's `status` description defines `settled` as every shown
path being committed or deliberately left with nothing story-owned unrecorded; it defines
`blocked` as an unresolved ownership, unsuitable commit, or failed commit that must park the run
for an operator. Its `notes` description records what was committed per package, or the paths
left behind and why they are not the story's.

Read `status` to decide whether the workflow may continue or must wait for an operator. Read
`notes` to learn the per-package record explaining that outcome. Neither field is preferred or
deprecated: both are required to communicate the result in their respective roles.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeSettled`
- rule: read `status` for the settlement decision and `notes` for its per-package record; the fields are complementary and have no ranking
