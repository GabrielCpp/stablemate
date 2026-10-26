"""The smoke benchmark's parts, shared by the fixtures and the tests that vary them."""

from __future__ import annotations

import subprocess
from pathlib import Path

BASE_CONFIG = """library_dir = "/nowhere"
default_cli = "claude"

[profiles.claude]
cli = "claude"
model = "base-model"
"""

SMOKE_TASKS = '''"""A task that writes a file, and scores it."""
from paddock import Score, score, step, task

task(name="smoke")

@step()
def touch(run):
    (run.repo / "made-by-the-step.txt").write_text("yes", encoding="utf-8")
    run.cli("/bin/sh", "-c", "echo hello", check=True)

@score()
def grade(run):
    return Score(headline="1/1 fine", detail=("one",), data={"caught": 1})
'''


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)
    return done.stdout.strip()


INTERRUPTIBLE_TASKS = '''"""A two-step task whose second step stops the round while `stop` exists beside the tasks module."""
import subprocess

from paddock import project, step, task
from paddock.runner import RoundInterrupted

task(name="smoke")

@step()
def first(run):
    with (run.workspace / "calls.txt").open("a", encoding="utf-8") as handle:
        handle.write("first\\n")
    (run.repo / "first.txt").write_text("1", encoding="utf-8")

@step()
def second(run):
    if (run.benchmark.root / "stop").exists():
        raise RoundInterrupted("operator stopped the phase")
    if run.pinned is not None and run.pinned.pinned:
        head = project.read(run.pinned, "rev-parse", "HEAD").stdout.strip()
        (run.repo / "pin-head.txt").write_text(head, encoding="utf-8")
    (run.repo / "second.txt").write_text("2", encoding="utf-8")
'''
