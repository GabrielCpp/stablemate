---
type: flow
slug: import-an-old-backlog-list
title: Import an old backlog list
---
# Import an old backlog list

- start: an old backlog list holds bullets written by hand
- steps:
  - [ostler backlog adopt](../planning.md#ostler-backlog-adopt)
- end: the caller reads how many records the list became
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^imported 2 records, kept 0 ids$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with an old two-bullet list beside it
