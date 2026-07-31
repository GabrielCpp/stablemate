"""The command table, and the one parser built from it.

Each subcommand is a module holding its own argument definition and its own body; this
module is only the table that maps a name to it. Adding a command is adding a module
and a row — never an `elif` in the entry point.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from workhorse.cli import config, dot, run, test, version


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
    Command(test.NAME, test.HELP, test.add_arguments, test.run),
    Command(dot.NAME, dot.HELP, dot.add_arguments, dot.run),
    Command(config.NAME, config.HELP, config.add_arguments, config.run),
    Command(version.NAME, version.HELP, version.add_arguments, version.run),
)

COMMANDS_BY_NAME: dict[str, Command] = {command.name: command for command in COMMANDS}


def build_parser(prog: str = "workhorse") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Fail-soft runner for agent workflows written as Python state "
        "machines.",
    )
    sub = parser.add_subparsers(dest="command")
    for command in COMMANDS:
        command.add_arguments(sub.add_parser(command.name, help=command.help))
    return parser
