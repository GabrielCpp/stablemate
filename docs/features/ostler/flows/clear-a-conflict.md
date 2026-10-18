---
type: flow
slug: clear-a-conflict
title: Clear a conflict
---
# Clear a conflict

- start: a human settled a story's conflict
- steps:
  - [ostler conflict clear](../planning.md#ostler-conflict-clear)
- end: the caller sees the conflict cleared
- verify: exit_status(code=0)
- verify: stdout(matches="^conflict cleared off 'charlie'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a story that carries a conflict
