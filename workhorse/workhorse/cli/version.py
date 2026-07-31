"""`workhorse version` — print the installed distribution version."""
from __future__ import annotations

import argparse
import importlib.metadata

NAME = "version"
HELP = "Print the installed workhorse-agent version"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """No arguments — declared anyway so every command in the table has the same shape."""


def run(args: argparse.Namespace) -> None:
    print(importlib.metadata.version("workhorse-agent"))
