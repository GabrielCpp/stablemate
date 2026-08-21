# tally backlog

Benchmark worklist for the symbol-granularity fixture. `tally` is a shared-expense ledger for a
trip: one JSON file in the working directory, five commands that read or change it, and no
service anywhere.

Surfaces this app ships:

- **tally** — a Python package under `tally/`, driven as `python -m tally`. It opens no port,
  serves no request and renders nothing. What it produces is an exit code, two streams, and the
  files it left on disk.

There is nothing to start and nothing to reach. A check here runs a command and reads what came
back, which is the property this fixture exists to exercise: a QA lane whose whole observable
vocabulary is process-shaped.

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope for
decomposition and none may be dropped.

## Starting a ledger for a trip and recording what was spent

## Loading a trip's expenses from a CSV file, twice if need be

## Reading the tally back, for a person and for a pipe
