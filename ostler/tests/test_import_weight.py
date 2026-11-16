"""A book or environment command does not load the planning graph."""

from __future__ import annotations

import subprocess
import sys


def run(code: str) -> str:
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return done.stdout.strip()


def test_the_book_and_environment_commands_leave_the_planning_graph_unloaded():
    code = ("import ostler.book.cli, ostler.environments.commands, sys; "
            "print('ostler.api' in sys.modules, 'ostler.model' in sys.modules)")
    assert run(code) == "False False"


def test_the_package_still_hands_out_its_planning_graph_names():
    assert run("from ostler import Ostler, Graph, load; print(Ostler.__name__, Graph.__name__, load.__name__)") == "Ostler Graph load"
