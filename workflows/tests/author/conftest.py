"""Shared fixtures for the author port's tests.

Every surveyor node resolves the consuming repo from its `repo_dir` argument, falling
back to the working directory, so a test is a real directory tree the `repo` fixture
stands in — no filesystem seam, no patched resolver, and nothing ambient. The
nodes themselves are the real ones: only the agent turn is ever scripted, and that
happens in the flow-level tests, where an agent turn exists.

The file helpers are fixtures rather than an importable module because the repo bans
relative imports outright, and `from author.helpers import write` would name a top-level
package that only exists while pytest has `tests/` on the path.
"""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def logger() -> logging.Logger:
    """The `logger` every node takes first. Diagnostics only — nothing asserts on it."""
    return logging.getLogger("test.author")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real git repo, pinned as the consuming repo for the duration of the test.

    Pinned by *chdir*, not by an environment variable: the resolvers read the run's
    `repo_dir` input and fall back to the working directory, so standing in the repo is
    what a node called with no `repo_dir` sees. A test that exercises the input itself
    passes `repo_dir=str(repo)` explicitly.
    """
    root = tmp_path / "acme"
    root.mkdir()
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL)
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def write() -> Callable[[Path, str], Path]:
    """Write text to a path, creating parents. Returns the path, for one-liners."""

    def _write(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_json(write: Callable[[Path, str], Path]) -> Callable[[Path, Any], Path]:
    """The same, for the inventory and the unit manifest."""

    def _write_json(path: Path, data: Any) -> Path:
        return write(path, json.dumps(data, indent=2) + "\n")

    return _write_json


@pytest.fixture
def read_json() -> Callable[[Path], Any]:
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    return _read_json
