---
type: spec.plan
---

# Plan: Read the Tally Back, for a Person and for a Pipe

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it.

## 1. Approach

A new module that does not print. `report.summarize` returns a dict and `report.export_rows`
writes a named file, so which stream a byte goes to is decided only in `cli.py` — which is what
makes the stdout rule enforceable rather than a habit.

`summarize` computes the total and the per-person figures in one pass, so the report can be
checked against itself. `export_rows` writes the header before it looks at the entries, so an
empty ledger exports a file with a header and no rows rather than an empty file.

## 2. Files

- `tally/report.py` — `summarize`, `export_rows`.
- `tally/cli.py` — adds the `report` and `export` subparsers, `cmd_report`, `cmd_export`.

## 3. Acceptance Checklist

- [x] `tally report` writes the count, the total and the per-person totals to stdout, exit `0`.
- [x] `tally report --json` puts exactly one JSON object on stdout and nothing else.
- [x] The total equals the sum of the per-person figures, in the currency `init` recorded.
- [x] `tally export PATH` writes every entry as CSV and exits `0`.
- [x] The exported file's first line is the header, empty ledger included.

## 4. QA

Same mechanism again, with one addition: the JSON scenario captures stdout and stderr
separately and parses stdout whole. Reading a JSON object out of a stream that also carries
progress lines is exactly the check this story exists to make impossible to pass by accident.
