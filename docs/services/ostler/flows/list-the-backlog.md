---
type: flow
slug: list-the-backlog
title: List the backlog
---
# List the backlog

- start: the caller wants the records one repository has on the debt register
- steps:
  - [ostler backlog list](../planning.md#ostler-backlog-list)
- end: the caller reads one tab-separated line per record of that repository
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^X-1\\tapi-service\\tbilling\\topen\\tuntriaged\\tfirst item$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with records X-1 and X-2 on its register
