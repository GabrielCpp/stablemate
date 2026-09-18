---
type: runbook
slug: run-tally
title: Run tally from a checkout
---
# Run tally from a checkout

- driver: cli
- environment: [The checkout itself](tally-checkout.md)
- surfaces: [tally](../tally.md)

This is a procedure, not a stack. There is nothing to bring up: no `entry-url`, no `launch`, no
`kind: service` step, and so nothing for QA to boot or tear down. What the steps establish is that
the command can be reached at all — that the package imports and the parser builds — after which
every claim the book makes is observed by invoking `tally` and reading what it left behind.

The distinction matters because a runbook with a service step promises a readiness contract: an
address, a health check, and a thing that is still running when the check arrives. None of those
is available here, and inventing them would mean checking a claim the book never made.

## Steps

### check-the-interpreter
- kind: prepare
- run: `python3 --version`
- verify: the interpreter is one `pyproject.toml`'s `requires-python` admits, which is what makes
  a later syntax error a defect in the product rather than in the machine

### build-the-parser
- kind: prepare
- run: `python3 -c "import tally.cli; tally.cli.build_parser()"`
- verify: the package imports from the checkout and every command, flag and default `tally`
  accepts is constructible — the same command `agents.yml` names as this service's regression

### show-the-usage
- kind: run
- run: `python3 -m tally --help`
- verify: the command is reachable over a process boundary and exits `0`, which is the only
  evidence a caller scripting `tally` can act on before it has a ledger to act against
