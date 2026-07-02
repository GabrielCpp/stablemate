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

from workhorse.scriptutil import resolve_workspace


def test_resolve_workspace_uses_agent_repo_dir_over_cwd():
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as workflow_dir:
        (Path(repo_dir) / "agents.yml").write_text("repo:\n  name: predykt\n")

        env = dict(os.environ)
        env.pop("CODER_WORKSPACE", None)
        env["AGENT_REPO_DIR"] = repo_dir
        with patch.dict(os.environ, env, clear=True):
            with patch("workhorse.scriptutil.Path.cwd", return_value=Path(workflow_dir)):
                repos = resolve_workspace("CODER_WORKSPACE")

        assert "predykt" in repos
        assert repos["predykt"]["path"] == str(Path(repo_dir).resolve())


def test_resolve_workspace_falls_back_to_cwd_without_agent_repo_dir():
    with tempfile.TemporaryDirectory() as repo_dir:
        (Path(repo_dir) / "agents.yml").write_text("repo:\n  name: predykt\n")

        env = dict(os.environ)
        env.pop("CODER_WORKSPACE", None)
        env.pop("AGENT_REPO_DIR", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("workhorse.scriptutil.Path.cwd", return_value=Path(repo_dir)):
                repos = resolve_workspace("CODER_WORKSPACE")

        assert "predykt" in repos
        assert repos["predykt"]["path"] == str(Path(repo_dir).resolve())
