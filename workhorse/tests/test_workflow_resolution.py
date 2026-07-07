"""Tests for --workflow library-name resolution and the cwd-based runs-dir default.

Covers two operator-ergonomics features of `workhorse run`:
  * `--workflow <name>` (a bare name, no path) resolves against the configured
    prompt library as <library_dir>/workflows/<name>/workflow.yaml; an explicit
    path is used verbatim.
  * `--runs-dir` defaults to <cwd>/.agents/runs — deduced from the launch dir,
    independent of where the workflow file lives.
"""
from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

m = importlib.import_module("workhorse.main")


# ── library-dir resolution ──────────────────────────────────────────────────

def test_library_dir_from_env_override():
    with patch.dict(os.environ, {"WORKHORSE_LIBRARY_DIR": "/tmp/lib"}, clear=False):
        assert m._resolve_library_dir() == Path("/tmp/lib")


def test_library_dir_from_workhorse_config():
    # library_dir falls back to workhorse's own config.toml (resolved via config_path();
    # WORKHORSE_CONFIG points it at a temp file here) when the env override is unset.
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "config.toml"
        cfg.write_text('library_dir = "/srv/agents"\n')
        env = {k: v for k, v in os.environ.items() if k != "WORKHORSE_LIBRARY_DIR"}
        env["WORKHORSE_CONFIG"] = str(cfg)
        with patch.dict(os.environ, env, clear=True):
            assert m._resolve_library_dir() == Path("/srv/agents")


def test_library_dir_none_when_unconfigured():
    with tempfile.TemporaryDirectory() as home:  # no config.toml inside
        env = {k: v for k, v in os.environ.items() if k != "WORKHORSE_LIBRARY_DIR"}
        env["WORKHORSE_CONFIG"] = str(Path(home) / "config.toml")
        with patch.dict(os.environ, env, clear=True):
            assert m._resolve_library_dir() is None


# ── --workflow resolution ───────────────────────────────────────────────────

def test_bare_name_resolves_against_library():
    with patch.object(m, "_resolve_library_dir", lambda: Path("/srv/agents")):
        assert m._resolve_workflow_path("author") == Path(
            "/srv/agents/workflows/author/workflow.yaml"
        )


def test_explicit_absolute_path_passes_through():
    with tempfile.TemporaryDirectory() as tmp:
        wf = Path(tmp) / "workflow.yaml"
        wf.write_text("name: x\n")
        # Even with a library configured, a path-like value is used verbatim.
        with patch.object(m, "_resolve_library_dir", lambda: Path("/srv/agents")):
            assert m._resolve_workflow_path(str(wf)) == wf.resolve()


def test_relative_path_is_not_treated_as_library_name():
    # Contains a separator → path, resolved against cwd, never the library.
    with patch.object(m, "_resolve_library_dir", lambda: Path("/srv/agents")):
        got = m._resolve_workflow_path("sub/workflow.yaml")
    assert got == (Path.cwd() / "sub" / "workflow.yaml").resolve()


def test_bare_name_without_library_errors():
    with patch.object(m, "_resolve_library_dir", lambda: None):
        try:
            m._resolve_workflow_path("author")
            raise AssertionError("expected SystemExit when no library configured")
        except SystemExit as e:
            assert e.code == 1


# ── runs-dir default = <cwd>/.agents/runs ───────────────────────────────────

def test_runs_dir_defaults_to_cwd_dot_agents_runs():
    captured = {}

    def fake_run(workflow_path, runs_dir, resume_run_dir=None, auto=True,
                 run_id=None, params=None, context_manifest=None, flow=None, no_cache=False):
        captured["runs_dir"] = runs_dir
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        launch = tmp / "repo"
        launch.mkdir()
        # Workflow lives somewhere ELSE — runs-dir must follow cwd, not the wf dir.
        wfdir = tmp / "elsewhere"
        wfdir.mkdir()
        wf = wfdir / "workflow.yaml"
        wf.write_text("name: research\n")
        with patch.object(m, "run", fake_run), patch.object(
            m.Path, "cwd", staticmethod(lambda: launch)
        ), patch("sys.argv", ["workhorse", "--workflow", str(wf)]):
            try:
                m.main()
            except SystemExit:
                pass
    assert captured["runs_dir"] == (launch / ".agents" / "runs").resolve()


# ── AGENT_REPO_DIR default = launch cwd ──────────────────────────────────────

def test_agent_repo_dir_defaults_to_launch_cwd():
    # Library scripts run with cwd = the workflow dir; AGENT_REPO_DIR must be
    # pinned to the launch dir so they resolve the consuming repo, not the library.
    def fake_run(*a, **k):
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        launch = tmp / "repo"
        launch.mkdir()
        wf = tmp / "elsewhere" / "workflow.yaml"
        wf.parent.mkdir()
        wf.write_text("name: research\n")
        env = {k: v for k, v in os.environ.items() if k != "AGENT_REPO_DIR"}
        with patch.dict(os.environ, env, clear=True), patch.object(
            m, "run", fake_run
        ), patch.object(
            m.Path, "cwd", staticmethod(lambda: launch)
        ), patch("sys.argv", ["workhorse", "--workflow", str(wf)]):
            try:
                m.main()
            except SystemExit:
                pass
            assert os.environ["AGENT_REPO_DIR"] == str(launch.resolve())


def test_agent_repo_dir_respects_explicit_value():
    # An explicitly-set AGENT_REPO_DIR (e.g. from the farrier Makefile) wins.
    def fake_run(*a, **k):
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        launch = tmp / "repo"
        launch.mkdir()
        wf = tmp / "elsewhere" / "workflow.yaml"
        wf.parent.mkdir()
        wf.write_text("name: research\n")
        with patch.dict(os.environ, {"AGENT_REPO_DIR": "/pinned/repo"}, clear=False), \
                patch.object(m, "run", fake_run), patch.object(
                    m.Path, "cwd", staticmethod(lambda: launch)
                ), patch("sys.argv", ["workhorse", "--workflow", str(wf)]):
            try:
                m.main()
            except SystemExit:
                pass
            assert os.environ["AGENT_REPO_DIR"] == "/pinned/repo"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
