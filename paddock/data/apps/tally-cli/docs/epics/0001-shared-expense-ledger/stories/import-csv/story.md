---
type: story
id: TALL-01M0JD6ET3BT2RSZH31G17H4RZ
slug: import-csv
status: Not started
---
# Story: Load a trip's expenses from a CSV file, twice if need be

## Dependencies

- Blocked by: ledger-init-add

## Fixtures

- Fixture: disk

## Context

Nobody types a trip in one expense at a time. `tally import` takes the file the bank or the
other person exported and adds what it holds.

The two rules here are both about what happens on the second run, because the second run is
the normal one. An import that failed partway would leave a ledger that is neither the old one
nor the new one, and the caller cannot tell which rows landed — so a file with a bad row is
refused whole, with the line number, and nothing is written. And an import that ran fine but
whose message went unread gets run again, so adding the rows the ledger does not already hold
is what makes "run it again" the right advice instead of a way to double the trip.

## Acceptance Criteria

- `tally import PATH` adds every expense in the file that the ledger does not already hold, and
  exits `0`.
- Importing the same file twice leaves the ledger holding exactly what importing it once left
  it holding.
- A file with a row that is not an expense is refused whole: exit `2`, no row added, and the
  message names the 1-based line of the offending row.
- A file whose header is not `who,what,amount_cents,spent_on` is refused the same way.
- `tally import --dry-run` reports what it would have added and leaves every file on disk
  byte-for-byte unchanged.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `tally/ledger.py::add_entry` is the one writer of an entry, and the one place an amount is
  checked — argparse deliberately does not do it, so `add` and `import` refuse the same values
  for the same reason.
- `tally/ledger.py::save` writes the whole document through a temp file and `os.replace`, which
  is what makes a refused import leave the previous ledger rather than half of a new one.
- `tally/cli.py::commit_or_preview` is the existing `--dry-run` seam: one place decides whether
  a command reaches the disk, so a new writer does not re-establish what the flag means.
- `tally/cli.py::main` translates `LedgerError` to exit 1 and `RowError` to exit 2 for every
  command, so a new command earns both exits by raising rather than by returning a code.

## Implementation Status

- **Status**: Not started
