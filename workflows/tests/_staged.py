from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def stage(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")
    _ = subprocess.run(["git", "add", rel], cwd=str(root), check=True, capture_output=True)


def run_check(script: Path, root: Path, *pathspecs: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *pathspecs], cwd=str(root), capture_output=True, text=True, check=False
    )
