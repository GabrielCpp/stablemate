---
type: flow
slug: pick-the-next-epic
title: Pick the next epic
---
# Pick the next epic

- start: a plan repo has several epics with unfinished work
- steps:
  - [ostler next epic](../planning.md#ostler-next-epic)
- end: the caller reads the first epic's name and its story count
- verify: exit_status(code=0)
- verify: json_path(path="name", equals="0001-first")
- verify: json_path(path="stories", equals=9)
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with four epics, the first holding nine unfinished stories
