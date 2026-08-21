---
type: spec.plan
---

# Plan: Load a Trip's Expenses From a CSV File, Twice if Need Be

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it.

## 1. Approach

Two functions in `ledger.py`, and the split between them is the story. `parse_rows` turns a
whole CSV document into entries or refuses the whole document, so nothing is written on a file
with a bad row anywhere in it. `merge` decides what is new, keyed on the whole expense, so a
second import of the same file adds nothing.

The amount goes through the same `_cents` a command-line `add` goes through. A `type=int` on
the parser would have let a CSV row in through a door the command line is closed to.

## 2. Files

- `tally/ledger.py` — adds `COLUMNS`, `key`, `parse_rows`, `merge`.
- `tally/cli.py` — adds the `import` subparser and `cmd_import`.

## 3. Acceptance Checklist

- [x] `tally import PATH` adds every expense the ledger does not already hold and exits `0`.
- [x] Importing the same file twice leaves the same ledger as importing it once.
- [x] A row that is not an expense refuses the whole file, exits `2`, and names its line.
- [x] A wrong header is refused the same way.
- [x] `--dry-run` reports what it would have added and writes nothing.

## 4. QA

Same mechanism as story 1 — `python3 -m tally`, with `--file` naming a ledger the scenario owns
— plus a CSV file the scenario lays down first, written by the same process boundary rather
than by the plan. The second import is the assertion, not a repetition of the first.
