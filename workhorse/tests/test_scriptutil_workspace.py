"""Tests for scriptutil.resolve_workspace's CWD-fallback branch.

Covers the mono-repo case: no workspace-file env var set, so resolve_workspace
must key the single-folder workspace off the actual repo root, not the cwd of
the subprocess that invoked it. Script nodes run with cwd = the workflow
definition's own directory (see main.py's AGENT_REPO_DIR comment), so a bare
Path.cwd() here would synthesize the wrong repo key whenever AGENT_REPO_DIR
and cwd diverge.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from workhorse.scriptutil import _git_network_command, resolve_workspace


def test_resolve_workspace_uses_agent_repo_dir_over_cwd():
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as workflow_dir:
        (Path(repo_dir) / "agents.yml").write_text("repo:\n  name: acme\n")

        env = dict(os.environ)
        env.pop("CODER_WORKSPACE", None)
        env["AGENT_REPO_DIR"] = repo_dir
        with patch.dict(os.environ, env, clear=True):
            with patch("workhorse.scriptutil.Path.cwd", return_value=Path(workflow_dir)):
                repos = resolve_workspace("CODER_WORKSPACE")

        assert "acme" in repos
        assert repos["acme"]["path"] == str(Path(repo_dir).resolve())


def test_resolve_workspace_falls_back_to_cwd_without_agent_repo_dir():
    with tempfile.TemporaryDirectory() as repo_dir:
        (Path(repo_dir) / "agents.yml").write_text("repo:\n  name: acme\n")

        env = dict(os.environ)
        env.pop("CODER_WORKSPACE", None)
        env.pop("AGENT_REPO_DIR", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("workhorse.scriptutil.Path.cwd", return_value=Path(repo_dir)):
                repos = resolve_workspace("CODER_WORKSPACE")

        assert "acme" in repos
        assert repos["acme"]["path"] == str(Path(repo_dir).resolve())


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
