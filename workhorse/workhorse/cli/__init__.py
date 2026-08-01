"""The command line a *workflow* binds — the only one workhorse ships.

Workhorse is a library. It drives no command of its own: there is no `workhorse`
executable, no name-to-workflow resolution, and no catalogue of what is installed. What
lives here is the wiring a workflow distribution uses to give its own workflow a command
line, so that every workflow gets the same flags without hand-writing an argument parser
that would drift from the engine it feeds::

    # in the workflow's module
    main = console_script(workflow.entry_point(Coder))

    # in the distribution's pyproject
    [project.scripts]
    workhorse-coder = "workhorse_workflows.coder.workflow:main"

This package parses argv, resolves the subcommand and hands off. Each command's
arguments and body live together in its own module (`run`, `dot`, `version`); `parser`
holds the table that maps a name to one.
"""
from __future__ import annotations

import sys
from typing import Protocol

from workhorse.cli.parser import COMMANDS_BY_NAME, build_parser
from workhorse.pyflow.registry import Registry


class ConsoleEntry(Protocol):
    """What a `[project.scripts]` target is: a callable that also carries a name.

    The name is not decoration — `entry.__name__` is what a workflow's script is
    known as, and the reason `console_script` sets it rather than leaving every
    workflow's entry point called `entry`.
    """

    __name__: str

    def __call__(self, argv: list[str] | None = None) -> None: ...

_SUBCOMMANDS = frozenset(COMMANDS_BY_NAME)
_DEFAULT_COMMAND = "run"


def main(
    argv: list[str] | None,
    *,
    workflow: str,
    registry: Registry,
) -> None:
    """One workflow's whole command line.

    ``argv`` defaults to the process arguments, so a console script calls this with
    none. ``workflow`` and ``registry`` are the workflow this command *is* — the script
    is inside the distribution and so holds the object already. Both are required:
    passing the registry is what lets the command work with the package merely on
    ``sys.path``, and it is why nothing here has to go looking for an installed
    distribution by name."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(prog=f"workhorse-{workflow}", workflow=workflow)

    # Running the workflow is what the command is for, so `run` is what a bare argv
    # means: `workhorse-coder qa` is `workhorse-coder run qa`.
    # Exception: bare --help/-h should show the subcommand listing.
    if argv and argv[0] in ("-h", "--help"):
        pass  # let the top-level parser handle it
    elif not argv or argv[0] not in _SUBCOMMANDS:
        argv = [_DEFAULT_COMMAND] + list(argv)

    args = parser.parse_args(argv)
    args.registry = registry
    args.workflow = workflow

    COMMANDS_BY_NAME[args.command or _DEFAULT_COMMAND].run(args)


def console_script(workflow: Registry) -> ConsoleEntry:
    """Build the callable a workflow's console script points at.

    ``[project.scripts]`` targets are *called* after import, so this returns the entry
    function rather than running anything — a module-level call would fire on import and
    could not be a script target at all.

    The argument is the workflow's own ``Registry``, which the module declaring the
    script already holds. Binding lives *here*, in the CLI ring, because the CLI is what
    a console script starts: a workflow module importing this is one arrow inward,
    whereas the registry building the callable itself needed an arrow back out to the
    CLI, which is a cycle."""
    if not isinstance(workflow, Registry):
        raise TypeError(
            "console_script() takes the workflow's own Registry — the object "
            "`workflow.entry_point(SomeWorkflow)` returns — not "
            f"{type(workflow).__name__}. A name is no longer enough: workhorse resolves "
            "no workflow by name, so the script must carry the registry it runs."
        )
    name = workflow.name

    def entry(argv: list[str] | None = None) -> None:
        main(argv, workflow=name, registry=workflow)

    entry.__name__ = f"workhorse_{name.replace('-', '_')}"
    entry.__qualname__ = entry.__name__
    entry.__doc__ = f"Console-script entry point for the '{name}' workflow."
    return entry


__all__ = ["build_parser", "console_script", "main"]
