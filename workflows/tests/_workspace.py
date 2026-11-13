"""A multi-repo workspace on disk: the artifacts repo and two code repos, each with one commit."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from workhorse._vendor.stablemate_core import config as core_config

Git = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Workspace:
    artifacts: Path
    api: Path
    web: Path


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env)


def _code_repo(root: Path, git: Git, *files: tuple[str, str]) -> Path:
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for name, text in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Initial commit")
    return root


def name_members(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspace: Workspace) -> None:
    config = tmp_path / "home-config.toml"
    config.write_text(
        f'[workspaces]\nacme = [{{ path = "{workspace.api}", name = "api" }}, '
        f'{{ path = "{workspace.web}", name = "web" }}]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def lay_out(tmp_path: Path, git: Git) -> Workspace:
    artifacts = core_config.ensure_artifacts_repo()
    git(artifacts, "add", ".gitignore")
    git(artifacts, "commit", "-qm", "Initial commit", "--allow-empty")
    api = _code_repo(
        tmp_path / "api",
        git,
        ("agents.yml", "repo:\n  id_prefix: X\n"),
        ("services/README.md", "# the app's own services folder\n"),
    )
    web = _code_repo(tmp_path / "web", git, ("README.md", "# web\n"))
    return Workspace(artifacts, api, web)
