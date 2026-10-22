"""The docs repo and the code workspace every `fix` flow test drains against."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from coder.fix.scripted import BACKLOG


@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """The docs repo, carrying a backlog with one drainable item and nothing else."""
    write(repo / "docs" / "backlog.md", BACKLOG)
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    name_workspace: Callable[[dict[str, Path]], None],
) -> dict[str, Path]:
    """Two real code repos and the named workspace that lists them, outside the docs tree."""
    root = tmp_path / "ws"
    repos: dict[str, Path] = {}
    for name in ("api", "web"):
        path = root / name
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        write(path / "README.md", f"# {name}\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "Initial commit")
        repos[name] = path
    name_workspace(repos)
    return repos
