---
type: cli
slug: tally
title: tally
---
# tally

- binary: tally
- code: tally/cli.py::main
- code: tally/__main__.py
- code: tally/__init__.py
- code: pyproject.toml

`tally` keeps one shared-expense ledger in one JSON file — `tally.json` in the working directory,
or wherever `--file` points. Every command reads that file, and the two that change it rewrite the
whole of it.

The contract a caller scripts against is three-part: an exit code, two streams, and the files left
on disk. `0` means the command did what it says. `1` means the ledger is not in the state the
command needs — there is already one, or there is not one yet — and that is a decision for the
caller. `2` means the data handed over is not an expense, which the caller fixes by editing their
input. Every human-facing line goes to stderr; stdout carries only what was asked for.

## Commands

### init
- usage: `tally init [--currency CODE]`
- parent: [tally](#tally)
- flags:
  - `--currency CODE`
    - type: string
    - required: false
    - default: `EUR`
- args:
  - none: `init` accepts no positional arguments.
- does:
  - Creates the ledger — `tally.json` here, unless `--file` names another — with no entries and
    the given currency.
- code: tally/cli.py::cmd_init
- detail: [The ledger file](concepts/ledger-file.md)

### add
- usage: `tally add WHO WHAT AMOUNT_CENTS SPENT_ON [--dry-run]`
- parent: [tally](#tally)
- flags:
  - `--dry-run`
    - type: boolean
    - required: false
    - default: `false`
- args:
  - `WHO`: who paid.
  - `WHAT`: what for.
  - `AMOUNT_CENTS`: a positive whole number of cents.
  - `SPENT_ON`: the day, as `YYYY-MM-DD`.
- does:
  - Records one expense in the ledger.
- code: tally/cli.py::cmd_add

### import
- usage: `tally import PATH [--dry-run]`
- parent: [tally](#tally)
- flags:
  - `--dry-run`
    - type: boolean
    - required: false
    - default: `false`
- args:
  - `PATH`: a CSV file whose header is `who,what,amount_cents,spent_on`.
- does:
  - Adds every expense in the file that the ledger does not already hold.
- code: tally/cli.py::cmd_import

## Invocations

### init-a-ledger
- on: [init](#init)
- trigger: the caller runs `tally init` in a directory.
- when: `tally.json` may or may not already be there.
- does:
  - Writes an empty ledger when there is none, and exits `0`.
  - Refuses when there is one already, and leaves that file byte-for-byte unchanged.
- verify: created(subject="tally.json")
- verify: unchanged(subject="tally.json")
- status: `0` when the ledger was created.
- verify: exit_status(code=0)
- status: `1` when a ledger was already there.
- verify: exit_status(code=1)
- code: tally/ledger.py::create

### add-an-expense
- on: [add](#add)
- trigger: the caller runs `tally add` against an existing ledger.
- does:
  - Appends the expense and rewrites the ledger.
- verify: count(subject="entries in the ledger", equals=1)
- verify: unchanged(subject="tally.json")
- status: `0` when the expense was recorded.
- verify: exit_status(code=0)
- status: `2` when the expense was refused.
- verify: exit_status(code=2)
- errors:
  - An amount that is not a positive whole number of cents is refused, and the ledger is left
    unchanged.
- code: tally/ledger.py::add_entry

### import-a-csv
- on: [import](#import)
- trigger: the caller runs `tally import` on a CSV file whose every row parses.
- does:
  - Adds the rows the ledger does not already hold, and no others.
  - Imports a row the file lists twice once: identity is the whole expense, within the file as
    much as against the ledger it lands in.
- verify: created(subject="the rows the ledger did not already hold")
- verify: count(subject="entries in the ledger", equals=3)
- verify: count(subject="entries the ledger holds for a row the file lists twice", equals=1)
- code: tally/ledger.py::merge
- consistency: ledger-file — importing the same file twice leaves the ledger holding what importing it once
  left it holding.

### import-a-malformed-row
- on: [import](#import)
- trigger: the caller runs `tally import` on a file with a row that is not an expense.
- does:
  - Refuses the whole file, so the ledger ends the invocation exactly as it began it.
- verify: unchanged(subject="tally.json")
- status: `2`.
- verify: exit_status(code=2)
- errors:
  - The message names the 1-based line number of the offending row.
- code: tally/ledger.py::parse_rows

### import-without-a-ledger
- on: [import](#import)
- trigger: the caller runs `tally import` in a directory with no ledger.
- does:
  - Refuses — there is nothing to import into until `tally init` has run — and conjures
    nothing: the invocation ends with the directory still holding no ledger.
- verify: unchanged(subject="the working directory")
- status: `1`.
- verify: exit_status(code=1)
- errors:
  - The message says the ledger does not exist and names `tally init` as the fix.
- code: tally/ledger.py::load

## Fields

### dry-run
- type: boolean
- default: `false`
- required: false
- semantics: with `--dry-run`, `add` and `import` leave every file on disk byte-for-byte as it
  was.
- semantics: a dry run makes no write at all — it does not write and roll back, nor write
  somewhere else instead.
- semantics: a dry run still reports what the command would have done, on stderr, and still
  exits `0`.
- code: tally/cli.py::commit_or_preview

### file
- type: path
- default: `tally.json`
- required: false
- semantics: every command acts on the ledger `--file` names, so two ledgers in the same directory
  never see each other.
- semantics: `--file` is global — it is given before the command, and one invocation names one
  ledger.
- code: tally/cli.py::build_parser

### currency
- type: string
- default: `EUR`
- required: false
- semantics: the currency is recorded once, at `init`, and every later report states that same
  code. `tally` converts nothing, so no later invocation may change it.
- code: tally/ledger.py::currency_of
