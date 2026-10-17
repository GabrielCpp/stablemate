---
type: spec.plan
---

# Plan: Start a Ledger, and Record One Expense at a Time

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it.

## 1. Approach

A stdlib-only Python package driven as `python -m tally`. `tally/cli.py` owns argument parsing,
the streams and the exit codes; `tally/ledger.py` owns the file and every rule about what may go
into it. Nothing in `ledger.py` prints and nothing in `cli.py` decides what an expense is, so a
rule holds identically however it was reached.

The two exception types are the exit vocabulary. `LedgerError` is about the state of the world
and exits `1`; `RowError` is about the data handed over and exits `2`. Both are translated in
`main` and nowhere else, so a command cannot forget.

## 2. Files

- `tally/__init__.py` — import-only package docstring.
- `tally/__main__.py` — the process boundary; hands `main`'s return value to the interpreter.
- `tally/cli.py` — the parser, `commit_or_preview`, `cmd_init`, `cmd_add`, `main`.
- `tally/ledger.py` — `create`, `load`, `save`, `currency_of`, `add_entry`, `_cents`.
- `pyproject.toml` — no dependencies; present so the package and the service marker resolve.

## 3. Acceptance Checklist

- [x] `tally init` writes an empty ledger with the given currency and exits `0`.
- [x] `tally init` where one exists refuses, exits `1`, and leaves the file unchanged.
- [x] `tally add` records one expense, on disk before it exits, and exits `0`.
- [x] An amount that is not a positive whole number of cents exits `2` with nothing written.
- [x] `--dry-run` leaves every file byte-for-byte unchanged and still exits `0`.

## 4. QA

Nothing to start and nothing to reach over a socket — but nothing to import either. A scenario
runs `python3 -m tally` through the `python3` tool `agents.yml` opts into, names its own ledger
with `--file`, and reads what came back: the exit code, the two streams, and the bytes on disk.
The refusals are the point of this story, and a refusal that leaves the file alone is only
provable by comparing the file to itself.
