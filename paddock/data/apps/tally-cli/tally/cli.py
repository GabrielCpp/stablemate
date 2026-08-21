"""The command line: parse an invocation, run it, turn what it raised into an exit code.

Every human-facing line this module writes goes to stderr, and stdout carries only the thing
the caller asked for. That is not a style rule — `tally report --json` is meant to be piped,
and a progress line on stdout does not degrade the report, it makes it unparseable.

The exit codes are the other half of the contract: 0 for done, 1 for a ledger that is not in
the state the command needs, 2 for input that is not an expense. A caller scripting `tally`
distinguishes "fix your file" from "decide what you meant" without reading a message.
"""

import argparse
import json
import sys
from pathlib import Path

from tally import ledger, report
from tally.ledger import LedgerError, RowError


def build_parser() -> argparse.ArgumentParser:
    """Every command `tally` accepts, the flags each one takes, and the ledger they act on.

    `--file` is declared here, on the top-level parser rather than on each command, because
    one invocation acts on one ledger: a global option cannot be given two different values
    by two subcommands, and every command below reads it off the same namespace.
    """
    parser = argparse.ArgumentParser(prog="tally", description="a shared-expense ledger")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("tally.json"),
        help="the ledger to read and write (default: tally.json, here)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    started = commands.add_parser("init", help="create an empty ledger here")
    started.add_argument("--currency", default="EUR", help="the currency the ledger records")
    started.set_defaults(handler=cmd_init)

    added = commands.add_parser("add", help="record one expense")
    added.add_argument("who")
    added.add_argument("what")
    added.add_argument("amount_cents")
    added.add_argument("spent_on")
    added.add_argument("--dry-run", action="store_true", help="report, change nothing")
    added.set_defaults(handler=cmd_add)

    imported = commands.add_parser("import", help="add every expense in a CSV file")
    imported.add_argument("path")
    imported.add_argument("--dry-run", action="store_true", help="report, change nothing")
    imported.set_defaults(handler=cmd_import)

    reported = commands.add_parser("report", help="total the ledger")
    reported.add_argument("--json", action="store_true", help="write one JSON object to stdout")
    reported.set_defaults(handler=cmd_report)

    exported = commands.add_parser("export", help="write the ledger out as CSV")
    exported.add_argument("path")
    exported.set_defaults(handler=cmd_export)

    return parser


def commit_or_preview(path: Path, data: dict, dry_run: bool) -> bool:
    """Write the ledger, unless this was a dry run — the one place that decision is made.

    Both writing commands route through here so `--dry-run` cannot mean one thing for `add`
    and another for `import`. A dry run leaves every file on disk byte-for-byte as it was;
    it does not write and roll back, and it does not write somewhere else.
    """
    if dry_run:
        print(f"tally: --dry-run, {path} left unchanged", file=sys.stderr)
        return False
    ledger.save(path, data)
    return True


def cmd_init(args: argparse.Namespace) -> int:
    """`tally init` — put an empty ledger here, if there is not one already."""
    ledger.create(args.file, args.currency)
    print(f"tally: created {args.file} in {args.currency}", file=sys.stderr)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """`tally add` — record one expense."""
    data = ledger.load(args.file)
    entry = ledger.add_entry(data, args.who, args.what, args.amount_cents, args.spent_on)
    if commit_or_preview(args.file, data, args.dry_run):
        print(f"tally: added {entry['amount_cents']} for {entry['who']}", file=sys.stderr)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    """`tally import` — add every expense in a CSV file that is not already recorded."""
    rows = ledger.parse_rows(Path(args.path).read_text(encoding="utf-8"))
    data = ledger.load(args.file)
    added = ledger.merge(data, rows)
    if commit_or_preview(args.file, data, args.dry_run):
        print(f"tally: imported {len(added)} of {len(rows)} rows", file=sys.stderr)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """`tally report` — what the ledger totals, for a person or for a pipe."""
    data = ledger.load(args.file)
    summary = report.summarize(data)
    if args.json:
        # Exactly one object, and nothing else. The note below is on stderr because a caller
        # who piped this is parsing stdout and cannot skip a line they did not expect.
        print(f"tally: totalling {summary['entries']} entries", file=sys.stderr)
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    print(f"{summary['entries']} entries, {summary['total_cents']} {summary['currency']}")
    for who, cents in summary["per_person"].items():
        print(f"  {who}: {cents}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """`tally export` — write the ledger out as CSV, header first."""
    data = ledger.load(args.file)
    written = report.export_rows(data, Path(args.path))
    print(f"tally: exported {written} rows to {args.path}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run one invocation and hand back its exit code.

    The two exception types are translated here and nowhere else, so every command exits 1 on
    a ledger-state problem and 2 on bad data without each one remembering to.
    """
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except LedgerError as bad:
        print(f"tally: {bad}", file=sys.stderr)
        return 1
    except RowError as bad:
        print(f"tally: {bad}", file=sys.stderr)
        return 2
