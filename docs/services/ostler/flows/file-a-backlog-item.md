---
type: flow
slug: file-a-backlog-item
title: File a backlog item
---
# File a backlog item

- start: the artifacts repo holds no record yet
- steps:
  - [ostler create backlog-item](../cli.md#ostler-create-backlog-item)
- end: the filed item is a record on the debt register with a fresh id
- verify: exit_status(code=0)
- fixture: none, because filing a fresh backlog item needs no seeded state
- detail: [Planning identities](../concepts/planning-identities.md)
