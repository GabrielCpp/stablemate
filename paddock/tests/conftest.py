"""Fixtures for paddock's own tests: a small repo, and a data directory around it."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


@pytest.fixture(autouse=True, scope="session")
def git_identity(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A global git identity, so the suite passes on identity-less machines.

    The fixture repos configure their own `user.*`, but a commit made through a pin's
    stashed git dir (a clone carries no local config), or in a repo a test `git init`ed
    mid-flight, falls back to the global config — which a CI runner does not have, so
    `git commit` dies there with "empty ident name" while passing on every developer
    machine. Pointing `GIT_CONFIG_GLOBAL` at a file of our own gives the fallback
    something to find anywhere, keeps repo-local identities winning, and stops the
    developer's real `~/.gitconfig` leaking into the suite. `data/tests/conftest.py`
    carries a twin of it, so both suites run under it — keep the two in step.
    """
    config = tmp_path_factory.mktemp("git-identity") / "gitconfig"
    config.write_text(
        "[user]\n\tname = paddock tests\n\temail = paddock@example.com\n",
        encoding="utf-8",
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CONFIG_GLOBAL", str(config))
        yield


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed repo with an executable script, a symlink, and an uncommitted edit."""
    root = tmp_path / "acme-api"
    (root / "cmd").mkdir(parents=True)
    (root / "README.md").write_text("acme\n", encoding="utf-8")
    script = root / "cmd" / "build.sh"
    script.write_text("#!/bin/sh\necho build\n", encoding="utf-8")
    script.chmod(0o755)
    (root / "latest").symlink_to("cmd/build.sh")
    git(root, "init", "--initial-branch", "main")
    git(root, "config", "user.email", "paddock@example.com")
    git(root, "config", "user.name", "paddock")
    git(root, "add", "-A")
    git(root, "commit", "-m", "initial")
    (root / "README.md").write_text("acme, edited\n", encoding="utf-8")
    return root


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "workspace" / "benchmarks"
    (directory / "tasks").mkdir(parents=True)
    (directory / "configs").mkdir(parents=True)
    (directory / "configs" / "test.toml").write_text('library_dir = "/nowhere"\n', encoding="utf-8")
    return directory


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "store"
