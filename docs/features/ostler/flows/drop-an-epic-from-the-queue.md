---
type: flow
slug: drop-an-epic-from-the-queue
title: Drop an epic from the queue
---
# Drop an epic from the queue

- start: an epic is no longer wanted next
- steps:
  - [ostler todo prune](../planning.md#ostler-todo-prune)
- end: the caller sees the epic pruned
- verify: exit_status(code=0)
- verify: stdout(matches="^pruned epic '0002-second' from the queue$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a queue that holds two epics
