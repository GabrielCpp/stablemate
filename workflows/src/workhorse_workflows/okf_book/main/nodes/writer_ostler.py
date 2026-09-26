"""The ostler the writer runs: `scaffold` and `fmt` only, a counted number of times, with their output clipped."""
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from ostler.cli import main as ostler_main

from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    OSTLER_MODULE,
    OSTLER_MAX_PRINTED_LINES,
    OSTLER_RUNS_SPENT_MESSAGE,
    CommandOutput,
    spend_ostler_run,
    printed_lines,
    run_quietly,
)

SUBCOMMANDS = ("scaffold", "fmt")
USAGE = f"usage: python -m {OSTLER_MODULE} <writer-commands.json> {{{','.join(SUBCOMMANDS)}}} <ostler arguments>"


def _ostler_exit_code(args: list[str]) -> int:
    try:
        return ostler_main(args)
    except SystemExit as exited:
        return exited.code if isinstance(exited.code, int) else 2


def run_ostler(argv: Sequence[str]) -> CommandOutput:
    """What one ostler run exits with and prints for command state file named first in `argv`."""
    if len(argv) < 2 or argv[1] not in SUBCOMMANDS:
        return CommandOutput(2, (USAGE,))
    if spend_ostler_run(Path(argv[0])) is None:
        return CommandOutput(1, (OSTLER_RUNS_SPENT_MESSAGE,))
    code, printed = run_quietly(lambda: _ostler_exit_code(list(argv[1:])))
    return CommandOutput(code, printed_lines(printed.splitlines(), OSTLER_MAX_PRINTED_LINES))


def main() -> int:
    """Run one ostler scaffold or fmt for the writer, and print the head of what it said."""
    return run_ostler(sys.argv[1:]).print_and_exit_code()


if __name__ == "__main__":
    sys.exit(main())
