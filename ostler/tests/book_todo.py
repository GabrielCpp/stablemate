"""The todo book of `fixtures/book_todo`, loaded the way an author's repo loads it, and a runner that plays it against the stand-in app."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

FIXTURE = Path(__file__).parent / "fixtures" / "book_todo"


def module(name: str) -> ModuleType:
    """A module of the fixture book, with the fixture's root on the import path."""
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    return importlib.import_module(name)


def runtime(port: int) -> dict[str, str]:
    """The environment a book run gets: the port the stand-in app listens on, and no import path."""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["TODO_API_PORT"] = str(port)
    return env


def run_book(arguments: list[str], port: int, cwd: Path = FIXTURE) -> subprocess.CompletedProcess[str]:
    """`python -m ostler.book` from the fixture's root, with the app on `port`."""
    return subprocess.run([sys.executable, "-m", "ostler.book", *arguments], cwd=cwd, env=runtime(port),
                          capture_output=True, text=True, check=False)
