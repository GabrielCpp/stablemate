"""The command table, and the one parser built from it."""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from workhorse.cli import control, dot, inbox, run, version


@dataclass(frozen=True, slots=True)
class Command:
    """One subcommand: its name, its help line, its arguments, and what it does."""

    name: str
    help: str
    add_arguments: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], None]


COMMANDS: tuple[Command, ...] = (
    Command(run.NAME, run.HELP, run.add_arguments, run.run),
    Command(dot.NAME, dot.HELP, dot.add_arguments, dot.run),
    Command(control.NAME, control.HELP, control.add_arguments, control.run),
    Command(inbox.NAME, inbox.HELP, inbox.add_arguments, inbox.run),
    Command(version.NAME, version.HELP, version.add_arguments, version.run),
)

COMMANDS_BY_NAME: dict[str, Command] = {command.name: command for command in COMMANDS}


def build_parser(prog: str, workflow: str) -> argparse.ArgumentParser:
    """The parser for one workflow's console script."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"Run the '{workflow}' workflow — a fail-soft agent workflow "
        "written as a Python state machine.",
    )
    sub = parser.add_subparsers(dest="command")
    for command in COMMANDS:
        command.add_arguments(sub.add_parser(command.name, help=command.help))
    return parser
