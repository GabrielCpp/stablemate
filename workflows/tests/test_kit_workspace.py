"""Tests for kit.workspace.resolve_workspace's single-repo fallback branch.

Covers the mono-repo case: no workspace file, so resolve_workspace must key the
single-folder workspace off the actual repo root rather than the cwd of the process
that invoked it. A node runs with cwd = wherever the driver was launched, which is
not necessarily the checkout under work, so a bare `Path.cwd()` here would synthesize
the wrong repo key whenever the run's `repo_dir` input and cwd diverge.

Both facts are **arguments**, not environment: `workspace_file` and `repo_dir` are
inputs of the run, so a test states them at the callsite the same way a workflow does.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from workhorse_workflows.kit.workspace import _git_network_command, resolve_workspace


def test_resolve_workspace_uses_the_repo_dir_argument_over_cwd():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
        repo_dir = Path(tmp) / "acme"
        repo_dir.mkdir()

        with patch("workhorse_workflows.kit.workspace.Path.cwd", return_value=Path(elsewhere)):
            repos = resolve_workspace(repo_dir=str(repo_dir))

        assert "acme" in repos
        assert repos["acme"]["path"] == str(repo_dir.resolve())


def test_resolve_workspace_falls_back_to_cwd_without_a_repo_dir():
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "acme"
        repo_dir.mkdir()

        with patch("workhorse_workflows.kit.workspace.Path.cwd", return_value=repo_dir):
            repos = resolve_workspace()

        assert "acme" in repos
        assert repos["acme"]["path"] == str(repo_dir.resolve())


def test_a_repo_is_named_by_its_directory_not_by_its_agents_yml():
    """agents.yml cannot rename a repo — the key here is also the install prefix
    farrier derives from the same directory, so a config that could override one and
    not the other would let a single checkout answer to two names."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "acme"
        repo_dir.mkdir()
        (repo_dir / "agents.yml").write_text("repo:\n  name: globex\n", encoding="utf-8")

        repos = resolve_workspace(repo_dir=str(repo_dir))

        assert list(repos) == ["acme"]


def test_git_network_command_uses_configured_token_env():
    with patch.dict(
        os.environ,
        {"WORKHORSE_GIT_TOKEN": "secret"},
        clear=True,
    ):
        command = _git_network_command("clone", "https://github.com/example/private.git")

    assert command[0:2] == ["git", "-c"]
    assert "credential.helper=" in command[2]
    assert "secret" not in command[2]
    assert "$WORKHORSE_GIT_TOKEN" in command[2]
    assert command[-2:] == ["clone", "https://github.com/example/private.git"]

def test_git_network_command_needs_no_token_for_public_or_local_clone():
    with patch.dict(os.environ, {}, clear=True):
        command = _git_network_command("clone", "/mnt/repo-src")

    assert command == ["git", "clone", "/mnt/repo-src"]
