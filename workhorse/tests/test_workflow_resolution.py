"""Tests for what `workhorse run` resolves around a workflow name.

A name resolves in exactly one place — an installed `workhorse.workflows` entry point
(covered in test_packaged_workflows.py). What is left for the CLI to decide, and what
these cover, is everything *around* that name, which is the CLI's contract rather than
the driver's:

  * `--runs-dir` defaults to <cwd>/.agents/runs — deduced from the launch dir, not from
    wherever the workflow package happens to be installed;
  * `AGENT_REPO_DIR` defaults to the launch cwd for the same reason, and an explicit
    value wins.
"""
from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

m = importlib.import_module("workhorse.main")


class _StubRegistry:
    """Stands in for the resolved Registry — the CLI only passes it through."""

    name = "acme-flow"


# ── runs-dir default = <cwd>/.agents/runs ───────────────────────────────────

def test_runs_dir_defaults_to_cwd_dot_agents_runs():
    captured = {}

    # Mirrors run_pyflow()'s real signature so a new driver argument shows up here as
    # a TypeError rather than silently going unpassed.
    def fake_run_pyflow(registry, flow=None, *, runs_dir, resume_run_dir=None,
                        run_id=None, params=None, no_cache=False, dry_run=False,
                        context_manifest=None, config=None):
        captured["runs_dir"] = runs_dir
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        launch.mkdir()
        with patch.object(m, "run_pyflow", fake_run_pyflow), patch.object(
            m, "_packaged_registry", lambda spec: _StubRegistry()
        ), patch.object(
            m.Path, "cwd", staticmethod(lambda: launch)
        ), patch("sys.argv", ["workhorse", "--workflow", "acme-flow"]):
            try:
                m.main()
            except SystemExit:
                pass
    assert captured["runs_dir"] == (launch / ".agents" / "runs").resolve()


# ── AGENT_REPO_DIR default = launch cwd ──────────────────────────────────────

def test_agent_repo_dir_defaults_to_launch_cwd():
    # A workflow's scripts run with a cwd that is not necessarily the consuming repo,
    # so AGENT_REPO_DIR is pinned to the launch dir for them to resolve it from.
    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        launch.mkdir()
        env = {k: v for k, v in os.environ.items() if k != "AGENT_REPO_DIR"}
        with patch.dict(os.environ, env, clear=True), patch.object(
            m, "run_pyflow", lambda *a, **k: 0
        ), patch.object(
            m, "_packaged_registry", lambda spec: _StubRegistry()
        ), patch.object(
            m.Path, "cwd", staticmethod(lambda: launch)
        ), patch("sys.argv", ["workhorse", "--workflow", "acme-flow"]):
            try:
                m.main()
            except SystemExit:
                pass
            assert os.environ["AGENT_REPO_DIR"] == str(launch.resolve())


def test_agent_repo_dir_respects_explicit_value():
    # An explicitly-set AGENT_REPO_DIR (e.g. from the farrier Makefile) wins.
    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        launch.mkdir()
        with patch.dict(os.environ, {"AGENT_REPO_DIR": "/pinned/repo"}, clear=False), \
                patch.object(m, "run_pyflow", lambda *a, **k: 0), patch.object(
                    m, "_packaged_registry", lambda spec: _StubRegistry()
                ), patch.object(
                    m.Path, "cwd", staticmethod(lambda: launch)
                ), patch("sys.argv", ["workhorse", "--workflow", "acme-flow"]):
            try:
                m.main()
            except SystemExit:
                pass
            assert os.environ["AGENT_REPO_DIR"] == "/pinned/repo"


# ── a path is no longer a workflow ───────────────────────────────────────────

def test_a_path_is_reported_as_a_path_not_as_an_unknown_name(capsys):
    """`--workflow ./workflows/coder/workflow.yaml` was the documented invocation for
    years. Reporting it as merely "no workflow named ..." would read as a bad install."""
    with patch.object(m, "find_packaged_workflow", lambda name: None), patch.object(
        m, "installed_workflow_names", list
    ):
        try:
            m._packaged_registry("./workflows/coder/workflow.yaml")
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("a path should not resolve to a workflow")
    err = capsys.readouterr().err
    assert "not workflow.yaml files" in err, err


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
