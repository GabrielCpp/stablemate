---
type: flow
slug: migrate-a-legacy-book-layout
title: Migrate a legacy book layout
---
# Migrate a legacy book layout

- start: the epics queue has not been turned into an index page yet
- verify: absent(subject="okf-migrate-fixture/docs/epics/index.md")
- steps:
  - [okf-migrate](../standalone-programs.md#okf-migrate)
- end: the legacy epic, its backlog queue and the untyped feature page are rewritten into OKF
  markdown
- verify: contents(subject="okf-migrate-fixture/docs/epics/sample-epic/epic.md", matches="(?s)^---\\ntype: epic\\n")
- fixture: [legacy book layout](../fixtures/legacy-book-layout.md)
- detail: [Migrating the legacy book layout](../concepts/migrating-the-legacy-book-layout.md)
