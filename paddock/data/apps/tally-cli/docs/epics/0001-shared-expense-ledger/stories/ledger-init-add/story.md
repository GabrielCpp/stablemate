---
type: story
id: TALL-01M0JD6ETM9X9R643G1M35BDK7
slug: ledger-init-add
status: Not started
---
# Story: Start a ledger, and record one expense at a time

## Dependencies

(none)

## Fixtures

- Fixture: disk

## Context

The first story is the package, the file it keeps, and the two commands that create and grow
it. Nothing is read back yet — `report` arrives in the third story — so everything this story
ships is observable only as an exit code and as the bytes left in `tally.json`.

Two refusals are in scope here rather than deferred, and both for the same reason: they are
the cases where the ledger is the only copy. `init` on a directory that already has one would
truncate a real trip on a mistyped command, and an amount that is not money would sit in the
file until somebody totalled it and disbelieved the answer.

`--dry-run` ships with `add` rather than after it. A flag that means "change nothing" and was
retrofitted is a flag whose meaning has to be re-established for each command it was added to.

## Acceptance Criteria

- `tally init` writes an empty ledger to `tally.json` in the working directory, recording the
  currency given by `--currency` and defaulting to `EUR`, and exits `0`.
- `tally init` run where a ledger already exists refuses, exits `1`, and leaves that file
  byte-for-byte unchanged.
- `tally add` records one expense and exits `0`, and the entry is on disk before it exits.
- An amount that is not a positive whole number of cents is refused with exit `2`, and the
  ledger is left unchanged.
- `tally add --dry-run` reports what it would have done, exits `0`, and leaves every file on
  disk byte-for-byte unchanged.
- Every human-facing line goes to stderr.

## Implementation Status

- **Status**: Not started
