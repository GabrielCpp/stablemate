---
type: flow
slug: read-the-epic-queue
title: Read the epic queue
---
# Read the epic queue

- start: the caller wants the order epics will run in
- steps:
  - [ostler todo list](../planning.md#ostler-todo-list)
- end: the caller reads one epic name per line
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^0001-first$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a queue that holds two epics
