"""The `workhorse` command line — the front door, and nothing else.

This package parses argv, resolves the subcommand, and hands off. Each command's
arguments and body live together in its own module (`run`, `test`, `dot`, `config`,
`version`); `parser` holds the table that maps a name to one. What remains here is the
part every front door shares: argv normalization, the per-workflow console script, and
the dispatch.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from workhorse.cli.parser import COMMANDS_BY_NAME, build_parser
from workhorse.pyflow.registry import Registry

_SUBCOMMANDS = frozenset(COMMANDS_BY_NAME)
_DEFAULT_COMMAND = "run"


def main(
    argv: list[str] | None = None,
    *,
    workflow: str | None = None,
    registry: Registry | None = None,
) -> None:
    """The whole CLI, for every front door there is.

    ``argv`` defaults to the process arguments, so the ``workhorse`` console script
    calls this with none. ``workflow`` names the workflow up front, which is what a
    per-workflow ``workhorse-<name>`` script binds — the *only* difference between the
    two commands. There is deliberately no second parser: a per-workflow script that
    grew its own argument definitions would drift from ``workhorse run`` silently, and
    the drift would only show up as two tools that disagree about a flag.

    ``registry`` is the Python workflow the caller already holds. A
    ``Registry.main(...)`` console script is inside the distribution and so has the
    object in hand; passing it skips entry-point discovery, which means the script
    still works when the package is on ``sys.path`` without being installed."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser("workhorse" if workflow is None else f"workhorse-{workflow}")

    # Keep `workhorse --workflow ...` working: if no recognised subcommand is
    # given, inject `run` so existing invocations are unchanged.
    # Exception: bare --help/-h should show the top-level subcommand listing.
    if argv and argv[0] in ("-h", "--help"):
        pass  # let the top-level parser handle it
    elif not argv or argv[0] not in _SUBCOMMANDS:
        argv = [_DEFAULT_COMMAND] + list(argv)

    args = parser.parse_args(argv)
    args.registry = registry
    if workflow is not None:
        _bind_workflow_name(parser, args, workflow)

    COMMANDS_BY_NAME[args.command or _DEFAULT_COMMAND].run(args)


def _bind_workflow_name(
    parser: argparse.ArgumentParser, args: argparse.Namespace, name: str
) -> None:
    """Fill in the workflow a per-workflow console script already knows.

    Parsing has happened by now: this only writes the name into the slot
    ``--workflow`` would have filled, and rejects the two ways the caller can
    contradict it."""
    command = getattr(args, "command", None)
    if command not in (None, "run"):
        parser.error(
            f"'{command}' is not available here — this command runs the '{name}' "
            f"workflow. Use `workhorse {command} ...` instead."
        )
    if getattr(args, "workflow", None) is not None:
        parser.error(
            f"--workflow is not accepted here: this command always runs '{name}'."
        )
    positional = getattr(args, "positional", None) or []
    if len(positional) > 1:
        extra = " ".join(positional[1:])
        parser.error(
            f"unexpected arguments: {extra} — usage: {parser.prog} run [<flow>] [options]"
        )
    args.workflow = name


def console_script(name: str) -> Callable[..., None]:
    """Build the callable a ``workhorse-<name>`` console script points at.

    ``[project.scripts]`` targets are *called* after import, so this returns the entry
    function rather than running anything — a module-level call would fire on import
    and could not be a script target at all."""

    def entry(argv: list[str] | None = None) -> None:
        main(argv, workflow=name)

    entry.__name__ = f"workhorse_{name.replace('-', '_')}"
    entry.__qualname__ = entry.__name__
    entry.__doc__ = f"Console-script entry point for the '{name}' workflow."
    return entry


__all__ = ["build_parser", "console_script", "main"]
