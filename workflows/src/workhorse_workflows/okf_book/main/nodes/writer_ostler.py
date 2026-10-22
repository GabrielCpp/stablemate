"""The ostler the writer runs: `scaffold`, `fmt`, a `gc` held to its own book and a `relink` of other books' links into it, a counted number of times, with their output clipped."""
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from ostler.book_reach import delete_pages
from ostler.cli import main as ostler_main

from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    OSTLER_MODULE,
    OSTLER_MAX_PRINTED_LINES,
    OSTLER_RUNS_SPENT_MESSAGE,
    CommandOutput,
    spend_ostler_run,
    printed_lines,
    read_command_state,
    run_quietly,
)
from workhorse_workflows.okf_book.shared.book_links import in_book, lands_in_book, relinked
from workhorse_workflows.okf_book.shared.entries import SERVICES_DIR
from workhorse_workflows.okf_book.shared.page_check import dead_book_pages

GC = "gc"
RELINK = "relink"
WRITE_OPTION = "--write"
SUBCOMMANDS = ("scaffold", "fmt", GC, RELINK)
USAGE = f"usage: python -m {OSTLER_MODULE} <writer-commands.json> {{{','.join(SUBCOMMANDS)}}} <ostler arguments>"
INDEX_DIR_OPTION = "--index-dir"
INDEX_DIR_REFUSED = f"{INDEX_DIR_OPTION} does not run here: ostler keeps its index outside the repository. Run the command without it."
GC_USAGE = f"usage: python -m {OSTLER_MODULE} <writer-commands.json> {GC} [{WRITE_OPTION}]"
NO_DEAD_PAGE = "every page of the book is linked from a page its entries page reaches"
RELINK_USAGE = (
    f"usage: python -m {OSTLER_MODULE} <writer-commands.json> {RELINK} <old> <new>, each a page of this book "
    "relative to its folder, with an optional #anchor"
)


def _ostler_exit_code(args: list[str]) -> int:
    try:
        return ostler_main(args)
    except SystemExit as exited:
        return exited.code if isinstance(exited.code, int) else 2


def _collect_garbage(state_path: Path, options: Sequence[str]) -> CommandOutput:
    if any(option != WRITE_OPTION for option in options):
        return CommandOutput(2, (GC_USAGE,))
    state = read_command_state(state_path)
    dead = [page for page in dead_book_pages(state.root) if page.service == state.service]
    write = WRITE_OPTION in options
    if write:
        delete_pages(dead)
    verb = "deleted" if write else f"would delete, with {WRITE_OPTION}:"
    return CommandOutput(0, printed_lines([f"{verb} {page.rel}" for page in dead] or [NO_DEAD_PAGE], OSTLER_MAX_PRINTED_LINES))


def _relink(state_path: Path, arguments: Sequence[str]) -> CommandOutput:
    state = read_command_state(state_path)
    service = state.service
    book = (SERVICES_DIR / service).as_posix()
    if len(arguments) != 2 or not all(lands_in_book(service, f"{book}/entries.md", target) for target in arguments):
        return CommandOutput(2, (RELINK_USAGE,))
    old, new = arguments
    said: list[str] = []
    for path in sorted((state.root / SERVICES_DIR).rglob("*.md")):
        page = path.relative_to(state.root).as_posix()
        if in_book(service, page):
            continue
        text, changed = relinked(service, page, path.read_text(encoding="utf-8"), old, new)
        if changed:
            _ = path.write_text(text, encoding="utf-8")
            said.append(f"relinked {changed} links on {page}")
    return CommandOutput(0, printed_lines(said or [f"no page of another book links to {old}"], OSTLER_MAX_PRINTED_LINES))


def run_ostler(argv: Sequence[str]) -> CommandOutput:
    """What one ostler run exits with and prints for command state file named first in `argv`."""
    if len(argv) < 2 or argv[1] not in SUBCOMMANDS:
        return CommandOutput(2, (USAGE,))
    if any(argument.split("=", 1)[0] == INDEX_DIR_OPTION for argument in argv[2:]):
        return CommandOutput(2, (INDEX_DIR_REFUSED,))
    if spend_ostler_run(Path(argv[0])) is None:
        return CommandOutput(1, (OSTLER_RUNS_SPENT_MESSAGE,))
    if argv[1] == GC:
        return _collect_garbage(Path(argv[0]), argv[2:])
    if argv[1] == RELINK:
        return _relink(Path(argv[0]), argv[2:])
    code, printed = run_quietly(lambda: _ostler_exit_code(list(argv[1:])))
    return CommandOutput(code, printed_lines(printed.splitlines(), OSTLER_MAX_PRINTED_LINES))


def main() -> int:
    """Run one ostler scaffold, fmt, gc or relink for the writer, and print the head of what it said."""
    return run_ostler(sys.argv[1:]).print_and_exit_code()


if __name__ == "__main__":
    sys.exit(main())
