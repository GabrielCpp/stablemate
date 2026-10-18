---
type: flow
slug: file-a-named-backlog-item
title: File a named backlog item
---
# File a named backlog item

- start: an idea needs a place under an id the caller picks
- steps:
  - [ostler backlog add](../planning.md#ostler-backlog-add)
- end: the caller sees the item filed
- verify: exit_status(code=0)
- verify: stdout(matches="^filed backlog item 'X-3'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a backlog of two named items
