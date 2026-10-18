---
type: flow
slug: find-the-story-behind-a-node
title: Find the story behind a node
---
# Find the story behind a node

- start: the caller names a node and supplies no source checkout
- steps:
  - [ostler query](../book-checks.md#ostler-query)
- end: the caller reads the node unresolved, with a warning that names the missing checkout
- verify: exit_status(code=0)
- verify: json_path(path="[0].resolved", equals=false)
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds a cli page that cites `src/demo.py::greet`
