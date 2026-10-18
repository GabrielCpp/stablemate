---
type: flow
slug: list-the-built-in-artifact-kinds
title: List the built-in artifact kinds
---
# List the built-in artifact kinds

- start: a caller does not yet know which artifact kinds ostler supports
- steps:
  - [ostler artifact list](../cli.md#ostler-artifact-list)
- end: the caller has the full ordered list of built-in kinds, including backlog-items
- verify: json_path(path="[2].kind", equals="backlog-items")
- fixture: none, because the kind registry is fixed in code, not read from any spec dir
