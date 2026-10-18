---
type: flow
slug: filter-the-book-graph
title: Filter the book graph
---
# Filter the book graph

- start: the caller wants the ids of every command node
- steps:
  - [ostler graph](../book-checks.md#ostler-graph)
- end: the caller reads one id per command node
- verify: exit_status(code=0)
- verify: stdout(matches="^docs/features/demo/cli\\.md#demo-greet$")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds one command node
