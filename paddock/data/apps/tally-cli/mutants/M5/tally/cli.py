"""The command line: parse an invocation, run it, turn what it raised into an exit code."""

import argparse
import sys
from pathlib import Path

from tally import ledger
from tally.ledger import LedgerError, RowError


def build_parser() -> argparse.ArgumentParser:
    """Every command `tally` accepts, the flags each one takes, and the ledger they act on."""
    parser = argparse.ArgumentParser(prog="tally", description="a shared-expense ledger")
    commands = parser.add_subparsers(dest="command", required=True)

    started = commands.add_parser("init", help="create an empty ledger here")
    started.add_argument(
        "--file",
        type=Path,
        default=Path("tally.json"),
        help="the ledger to read and write (default: tally.json, here)",
    )
    started.add_argument("--currency", default="EUR", help="the currency the ledger records")
    started.set_defaults(handler=cmd_init)

    added = commands.add_parser("add", help="record one expense")
    added.add_argument(
        "--file",
        type=Path,
        default=Path("tally.json"),
        help="the ledger to read and write (default: tally.json, here)",
    )
    added.add_argument("who")
    added.add_argument("what")
    added.add_argument("amount_cents")
    added.add_argument("spent_on")
    added.add_argument("--dry-run", action="store_true", help="report, change nothing")
    added.set_defaults(handler=cmd_add)

    return parser


def commit_or_preview(path: Path, data: dict, dry_run: bool) -> bool:
    """Write the ledger, unless this was a dry run — the one place that decision is made."""
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


def main(argv: list[str] | None = None) -> int:
    """Run one invocation and hand back its exit code."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except LedgerError as bad:
        print(f"tally: {bad}", file=sys.stderr)
        return 1
    except RowError as bad:
        print(f"tally: {bad}", file=sys.stderr)
        return 2
