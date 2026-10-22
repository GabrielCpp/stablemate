---
type: flow
slug: list-the-backlog
title: List the backlog
---
# List the backlog

- start: the caller wants every filed idea
- steps:
  - [ostler backlog list](../planning.md#ostler-backlog-list)
- end: the caller reads one JSON object per named item
- verify: exit_status(code=0)
- verify: stdout(matches="\"id\": \"X-1\"")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a backlog of two named items and one unnamed
