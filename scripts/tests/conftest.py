"""Put the guards under `scripts/` on the path, and build a repo for them to guard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


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
