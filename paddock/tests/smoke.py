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
from paddock import Score, step, task

task(name="smoke")

@step()
def touch(run):
    (run.repo / "made-by-the-step.txt").write_text("yes", encoding="utf-8")
    run.cli("/bin/sh", "-c", "echo hello", check=True)

def score(run):
    return Score(headline="1/1 fine", detail=("one",), data={"caught": 1})
'''


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)
    return done.stdout.strip()
