---
type: flow
slug: map-a-change-across-source-repositories
title: Map a change across source repositories
---
# Map a change across source repositories

- start: a change spans more than one checkout, each versioned on its own, and a caller already
  runs Python rather than shelling out to `ostler qa context --source-root`, which only ever
  addresses the one checkout the process runs from
- steps:
  - [qa-context-source-repository](../standalone-programs.md#qa-context-source-repository)
- end: the packet carries one `changedCode` entry per changed file tagged with the repository
  that owns it, plus one `repositories` row per checkout naming the commits its revisions
  resolved to
- verify: json_path(path="changedCode[0].repository", equals="demo-repo")
- verify: json_path(path="repositories[0].id", equals="demo-repo")
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md)
- detail: [Compiling a book into a QA plan](../concepts/compiling-a-book-into-a-qa-plan.md)
