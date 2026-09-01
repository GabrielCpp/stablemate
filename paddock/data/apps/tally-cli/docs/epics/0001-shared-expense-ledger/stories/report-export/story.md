---
type: story
id: TALL-01M0JD6ETPFDFXV1CFJWB9NJKF
slug: report-export
status: Not started
---
# Story: Read the tally back, for a person and for a pipe

## Dependencies

- Blocked by: import-csv

## Fixtures

- Fixture: disk

## Context

The last story is the reason for the first two: what the trip cost, and who put in what.

It ships in two shapes because it has two readers. A person runs `tally report` and reads
lines. Something downstream runs `tally report --json` and parses one object — which is where
the stream discipline the earlier stories adopted stops being a convention and starts being
load-bearing. A progress line on stdout does not make the report worse, it makes it
unparseable, and the failure surfaces in the caller rather than here.

`export` is the other half of handing the trip on: the same entries as CSV, header first,
including for an empty ledger. An export whose shape depends on its content is an export every
reader has to sniff before parsing.

## Acceptance Criteria

- `tally report` writes the entry count, the total and the per-person totals to stdout and
  exits `0`.
- `tally report --json` puts exactly one JSON object on stdout and nothing else; every
  human-facing line goes to stderr.
- The reported total equals the sum of the per-person totals, and the reported currency is the
  one the ledger was initialised with.
- `tally export PATH` writes every entry to `PATH` as CSV and exits `0`.
- The exported file's first line is the header `who,what,amount_cents,spent_on`, whether or not
  the ledger has entries.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `tally/ledger.py::load` reads the document back and is the only reader; `tally/ledger.py::currency_of`
  takes the currency from the ledger rather than from the invocation, because `tally` converts nothing.
- `tally/cli.py::build_parser` is where a subcommand attaches, and `tally/cli.py::main` is where its
  exceptions become exit codes.
- `tally/cli.py::commit_or_preview` shows the established stderr/stdout split every command follows.

## Implementation Status

- **Status**: Not started
