---
type: flow
slug: find-uncited-source
title: Find uncited source
---
# Find uncited source

- start: a source inventory lists a function no node of the book cites
- steps:
  - [ostler coverage](../book-checks.md#ostler-coverage)
- end: the caller is told which unit is missing, and the exit status stops a gate
- verify: exit_status(code=1)
- verify: json_path(path="missing[0].code", equals="src/demo.py::farewell")
- fixture: [book scratch repo](../fixtures/book-scratch-repo.md) — seeds an inventory of two functions, of which the book cites one
- detail: [Book health: coverage, reach and census](../concepts/book-health-coverage-reach-and-census.md)
