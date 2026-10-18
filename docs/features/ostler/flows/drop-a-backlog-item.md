---
type: flow
slug: drop-a-backlog-item
title: Drop a backlog item
---
# Drop a backlog item

- start: an idea was done or dropped
- steps:
  - [ostler backlog prune](../planning.md#ostler-backlog-prune)
- end: the caller sees the item pruned
- verify: exit_status(code=0)
- verify: stdout(matches="^pruned backlog item 'X-2'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a backlog of two named items
