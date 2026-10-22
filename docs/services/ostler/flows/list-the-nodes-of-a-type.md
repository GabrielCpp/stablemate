---
type: flow
slug: list-the-nodes-of-a-type
title: List the nodes of a type
---
# List the nodes of a type

- start: the caller wants every node of one type
- steps:
  - [ostler list](../book-checks.md#ostler-list)
- end: the caller reads one entry per node of that type
- verify: exit_status(code=0)
- verify: json_path(path="[0].type", equals="flow")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds one flow
