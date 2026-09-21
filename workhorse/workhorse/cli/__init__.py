"""The command line a *workflow* binds — the only one workhorse ships."""
from __future__ import annotations

import sys
from typing import Protocol

from workhorse.cli.parser import COMMANDS_BY_NAME, build_parser
from workhorse.pyflow.registry import Registry


class ConsoleEntry(Protocol):
    """What a `[project.scripts]` target is: a callable that also carries a name."""

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
    """One workflow's whole command line."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(prog=f"workhorse-{workflow}", workflow=workflow)

    if argv and argv[0] in ("-h", "--help"):
        pass
    elif not argv or argv[0] not in _SUBCOMMANDS:
        argv = [_DEFAULT_COMMAND] + list(argv)

    args = parser.parse_args(argv)
    args.registry = registry
    args.workflow = workflow

    COMMANDS_BY_NAME[args.command or _DEFAULT_COMMAND].run(args)


def console_script(workflow: Registry) -> ConsoleEntry:
    """Build the callable a workflow's console script points at."""
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
