---
type: flow
slug: file-a-backlog-item
title: File a backlog item
---
# File a backlog item

- start: no backlog file exists yet
- verify: absent(subject="docs/backlog.md")
- steps:
  - [ostler create backlog-item](../cli.md#ostler-create-backlog-item)
- end: the filed item is recorded in the backlog with a fresh id
- verify: contents(subject="docs/backlog.md", matches="(?m)^- \\[TEST-[0-9A-HJKMNP-TV-Z]{26}\\] a sample backlog item$")
- fixture: none, because filing a fresh backlog item needs no seeded state
- detail: [Planning identities](../concepts/planning-identities.md)
