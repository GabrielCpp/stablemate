---
type: flow
slug: file-a-backlog-item
title: File a backlog item
---
# File a backlog item

- start: a person has found work nobody has filed yet
- steps:
  - [ostler create backlog-item](../cli.md#ostler-create-backlog-item)
- end: the filed item is a record on the debt register with a fresh id
- verify: exit_status(code=0)
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with records X-1 and X-2 on its register
- detail: [The debt register](../concepts/the-debt-register.md)
- detail: [Planning identities](../concepts/planning-identities.md)
