---
type: flow
slug: reorder-the-epic-queue
title: Reorder the epic queue
---
# Reorder the epic queue

- start: the caller wants a different run order
- steps:
  - [ostler todo reorder](../planning.md#ostler-todo-reorder)
- end: the caller sees the queue rewritten
- verify: exit_status(code=0)
- verify: stdout(matches="^reordered epics queue$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a queue that holds 0001-first
