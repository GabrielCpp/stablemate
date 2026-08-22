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
- verify: created(subject="tally.json")
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
- verify: count(subject="entries in the ledger", equals=1)
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
- verify: created(subject="the rows the ledger did not already hold")
- code: tally/cli.py::cmd_import

### report
- usage: `tally report [--json]`
- parent: [tally](#tally)
- flags:
  - `--json`
    - type: boolean
    - required: false
    - default: `false`
- args:
  - none: `report` accepts no positional arguments.
- does:
  - Totals the ledger, per person and overall.
- verify: json_path(path="$.total_cents", equals="7450")
- code: tally/cli.py::cmd_report

### export
- usage: `tally export PATH`
- parent: [tally](#tally)
- flags:
  - none: `export` accepts no flags.
- args:
  - `PATH`: the CSV file to write.
- does:
  - Writes every entry in the ledger to `PATH` as CSV.
- verify: created(subject="the exported CSV file")
- code: tally/cli.py::cmd_export

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
- code: tally/ledger.py::create
- status: `0` when the ledger was created.
- status: `1` when a ledger was already there.

### add-an-expense
- on: [add](#add)
- trigger: the caller runs `tally add` against an existing ledger.
- does:
  - Appends the expense and rewrites the ledger.
- verify: count(subject="entries in the ledger", equals=1)
- verify: unchanged(subject="tally.json")
- code: tally/ledger.py::add_entry
- status: `0` when the expense was recorded.
- status: `2` when the expense was refused.
- errors:
  - An amount that is not a positive whole number of cents is refused, and the ledger is left
    unchanged.

### import-a-csv
- on: [import](#import)
- trigger: the caller runs `tally import` on a CSV file whose every row parses.
- does:
  - Adds the rows the ledger does not already hold, and no others.
- verify: created(subject="the rows the ledger did not already hold")
- verify: count(subject="entries in the ledger", equals=3)
- code: tally/ledger.py::merge
- consistency: ledger-file — importing the same file twice leaves the ledger holding what importing it once
  left it holding.

### import-a-malformed-row
- on: [import](#import)
- trigger: the caller runs `tally import` on a file with a row that is not an expense.
- does:
  - Refuses the whole file, so the ledger ends the invocation exactly as it began it.
- verify: unchanged(subject="tally.json")
- code: tally/ledger.py::parse_rows
- status: `2`.
- errors:
  - The message names the 1-based line number of the offending row.

### report-as-json
- on: [report](#report)
- trigger: the caller runs `tally report --json`, usually into a pipe.
- does:
  - Writes the totals as one JSON object.
- verify: json_path(path="$.currency", equals="EUR")
- code: tally/report.py::summarize
- consistency: command-output — stdout carries exactly that one JSON object and nothing else.
- consistency: command-output — every human-facing line the command writes goes to stderr.

### export-to-csv
- on: [export](#export)
- trigger: the caller runs `tally export` against an existing ledger.
- does:
  - Writes one CSV file holding every entry.
- verify: created(subject="the exported CSV file")
- code: tally/report.py::export_rows
- consistency: export-csv — the file's first line is the header `who,what,amount_cents,spent_on`, whether or
  not the ledger has entries.

## Fields

### dry-run
- type: boolean
- default: `false`
- required: false
- semantics: with `--dry-run`, `add` and `import` leave every file on disk byte-for-byte as it
  was.
- verify: unchanged(subject="tally.json")
- semantics: a dry run makes no write at all — it does not write and roll back, nor write
  somewhere else instead.
- verify: unchanged(subject="the working directory")
- semantics: a dry run still reports what the command would have done, on stderr, and still
  exits `0`.
- code: tally/cli.py::commit_or_preview

### file
- type: path
- default: `tally.json`
- required: false
- semantics: every command acts on the ledger `--file` names, so two ledgers in the same directory
  never see each other.
- verify: unchanged(subject="the ledger --file did not name")
- semantics: `--file` is global — it is given before the command, and one invocation names one
  ledger.
- code: tally/cli.py::build_parser

### currency
- type: string
- default: `EUR`
- verify: json_path(path="$.currency", equals="EUR")
- required: false
- semantics: the currency is recorded once, at `init`, and every later report states that same
  code. `tally` converts nothing, so no later invocation may change it.
- code: tally/ledger.py::currency_of
