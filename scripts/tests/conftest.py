"""Build a repo for the guards under `scripts/` to guard."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _artifacts_dir_is_per_test(tmp_path_factory, monkeypatch):
    """Specs live in the user's artifacts folder, so no test may resolve to the real one."""
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(tmp_path_factory.mktemp("artifacts")))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.name=gate", "-c", "user.email=gate@example.com",
            "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def strict_repo(root: Path, max_lines: int = 400) -> Path:
    (root / "pkg" / "strict").mkdir(parents=True)
    (root / "pkg" / "loose").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[tool.stablemate.strict]\npaths = ["pkg/strict"]\nmax-lines = {max_lines}\n',
        encoding="utf-8",
    )
    (root / "pkg" / "strict" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "pkg" / "loose" / "other.py").write_text("VALUE = 2\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return root
