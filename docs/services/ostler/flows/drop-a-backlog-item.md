---
type: flow
slug: drop-a-backlog-item
title: Drop a backlog item
---
# Drop a backlog item

- start: a record was fixed, dropped or promoted
- steps:
  - [ostler backlog prune](../planning.md#ostler-backlog-prune)
- end: the caller sees the record closed
- verify: exit_status(code=0)
- verify: stdout(matches="^closed record 'X-2' as done$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a record X-2 filed on its register
