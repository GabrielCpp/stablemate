---
type: concept
slug: attempt-ledger-field-roles
title: Attempt ledger field roles
---
# Attempt ledger field roles

`Ledger` returns both the location of the durable attempt ledger and the text currently available
from it. They are related values, not interchangeable representations: `record_attempt` reads or
updates the file at `ledger`, then returns its content as `prior_attempts`. The story-author flow
passes only `prior_attempts` to the rework prompt, while callers retain `ledger` as the
repository-relative file location.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Ledger`
- rule: use `ledger` to locate the attempt file; use `prior_attempts` when the rework prompt needs the failed approaches recorded in that file
