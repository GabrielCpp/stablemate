---
type: flow
slug: queue-an-epic
title: Queue an epic
---
# Queue an epic

- start: an epic is ready to be worked
- steps:
  - [ostler todo add](../planning.md#ostler-todo-add)
- end: the caller sees the epic queued
- verify: exit_status(code=0)
- verify: stdout(matches="^queued epic '0003-third'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a queue that holds two epics
