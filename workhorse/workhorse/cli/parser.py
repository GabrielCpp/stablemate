"""The command table, and the one parser built from it.

Each subcommand is a module holding its own argument definition and its own body; this
module is only the table that maps a name to it. Adding a command is adding a module
and a row — never an `elif` in the entry point.

The table is short on purpose. Workhorse is a library; the only command line it ships
is the one a *workflow* binds for itself with :func:`workhorse.console_script`, so a
subcommand earns its place only by being something the author of that workflow needs:
run it, draw it, say which engine version drew it.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from workhorse.cli import dot, run, version


@dataclass(frozen=True, slots=True)
class Command:
    """One subcommand: its name, its help line, its arguments, and what it does."""

    name: str
    help: str
    add_arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], None]


# `run` is first because it is the default: an argv whose first token names none of
# these gets `run` injected in front of it (see `workhorse.cli.main`).
COMMANDS: tuple[Command, ...] = (
    Command(run.NAME, run.HELP, run.add_arguments, run.run),
    Command(dot.NAME, dot.HELP, dot.add_arguments, dot.run),
    Command(version.NAME, version.HELP, version.add_arguments, version.run),
)

COMMANDS_BY_NAME: dict[str, Command] = {command.name: command for command in COMMANDS}


def build_parser(prog: str, workflow: str) -> argparse.ArgumentParser:
    """The parser for one workflow's console script.

    ``prog`` is the command the operator typed and ``workflow`` the workflow bound to
    it — usually the same word, but a distribution is free to name its script anything.
    Neither has a default: there is no generic front door left to be the fallback."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"Run the '{workflow}' workflow — a fail-soft agent workflow "
        "written as a Python state machine.",
    )
    sub = parser.add_subparsers(dest="command")
    for command in COMMANDS:
        command.add_arguments(sub.add_parser(command.name, help=command.help))
    return parser
