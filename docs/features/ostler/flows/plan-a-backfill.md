---
type: flow
slug: plan-a-backfill
title: Plan a backfill
---
# Plan a backfill

- start: a source inventory lists a function no node of the book cites
- steps:
  - [ostler backfill plan](../book-checks.md#ostler-backfill-plan)
- end: the caller reads the units the book owes the code, and the command still exits 0
- verify: exit_status(code=0)
- verify: json_path(path="units[0].unit", equals="src/demo.py::farewell")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds an inventory of two functions, of which the book cites one
