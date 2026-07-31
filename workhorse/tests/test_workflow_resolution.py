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

cli_mod = importlib.import_module("workhorse.cli")
resolve_mod = importlib.import_module("workhorse.cli.resolve")
run_cmd = importlib.import_module("workhorse.cli.run")


class _StubRegistry:
    """Stands in for the resolved Registry — the CLI only passes it through."""

    name = "acme-flow"


# ── runs-dir default = <cwd>/.agents/runs ───────────────────────────────────

def test_runs_dir_defaults_to_cwd_dot_agents_runs():
    captured = {}

    def fake_run_pyflow(invocation):
        captured["runs_dir"] = invocation.runs_dir
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        launch.mkdir()
        with patch.object(run_cmd, "run_pyflow", fake_run_pyflow), patch.object(
            run_cmd, "packaged_registry", lambda spec: _StubRegistry()
        ), patch.object(
            run_cmd.Path, "cwd", staticmethod(lambda: launch)
        ), patch("sys.argv", ["workhorse", "--workflow", "acme-flow"]):
            try:
                cli_mod.main()
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
            run_cmd, "run_pyflow", lambda invocation: 0
        ), patch.object(
            run_cmd, "packaged_registry", lambda spec: _StubRegistry()
        ), patch.object(
            run_cmd.Path, "cwd", staticmethod(lambda: launch)
        ), patch("sys.argv", ["workhorse", "--workflow", "acme-flow"]):
            try:
                cli_mod.main()
            except SystemExit:
                pass
            assert os.environ["AGENT_REPO_DIR"] == str(launch.resolve())


def test_agent_repo_dir_respects_explicit_value():
    # An explicitly-set AGENT_REPO_DIR (e.g. from the farrier Makefile) wins.
    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        launch.mkdir()
        with patch.dict(os.environ, {"AGENT_REPO_DIR": "/pinned/repo"}, clear=False), \
                patch.object(run_cmd, "run_pyflow", lambda invocation: 0), patch.object(
                    run_cmd, "packaged_registry", lambda spec: _StubRegistry()
                ), patch.object(
                    run_cmd.Path, "cwd", staticmethod(lambda: launch)
                ), patch("sys.argv", ["workhorse", "--workflow", "acme-flow"]):
            try:
                cli_mod.main()
            except SystemExit:
                pass
            assert os.environ["AGENT_REPO_DIR"] == "/pinned/repo"


# ── a path is no longer a workflow ───────────────────────────────────────────

def test_a_path_is_reported_as_a_path_not_as_an_unknown_name(capsys):
    """`--workflow ./workflows/coder/workflow.yaml` was the documented invocation for
    years. Reporting it as merely "no workflow named ..." would read as a bad install."""
    with patch.object(
        resolve_mod, "find_packaged_workflow", lambda name: None
    ), patch.object(resolve_mod, "installed_workflow_names", list):
        try:
            resolve_mod.packaged_registry("./workflows/coder/workflow.yaml")
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("a path should not resolve to a workflow")
    err = capsys.readouterr().err
    assert "not workflow.yaml files" in err, err


# ── --resume-run accepts what --run-id took ─────────────────────────────────

def _resume_target(argv: list[str], make: str) -> Path | None:
    """Run the CLI with `argv` against a runs dir holding one dir named `make`."""
    captured: dict[str, Path | None] = {}

    def fake_run_pyflow(invocation):
        captured["resume_run_dir"] = invocation.resume_run_dir
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        (launch / ".agents" / "runs" / make).mkdir(parents=True)
        with patch.object(run_cmd, "run_pyflow", fake_run_pyflow), patch.object(
            run_cmd, "packaged_registry", lambda spec: _StubRegistry()
        ), patch.object(
            run_cmd.Path, "cwd", staticmethod(lambda: launch)
        ), patch("sys.argv", ["workhorse", "--workflow", "acme-flow", *argv]):
            try:
                cli_mod.main()
            except SystemExit:
                pass
        return captured.get("resume_run_dir")


def test_resume_run_takes_the_run_id_that_named_the_dir():
    """`--run-id shakedown` creates `acme-flow-shakedown`, so `--resume-run shakedown`
    has to find it.

    The flag's metavar is `PATH_OR_RUN_ID` and it only ever resolved a path or the full
    dir *name* — so resuming a run with the same id you started it with failed, which is
    the one spelling anybody types. It matters more than a papercut: a run that will not
    resume is a run whose checkpoint is silently abandoned, and the fix for that is to
    start over."""
    target = _resume_target(["--resume-run", "shakedown"], make="acme-flow-shakedown")
    assert target is not None and target.name == "acme-flow-shakedown", target


def test_resume_run_still_takes_the_dir_name():
    """The documented spelling keeps working, and keeps winning: a dir that matches the
    argument outright is never re-read as a run id."""
    target = _resume_target(["--resume-run", "acme-flow-shakedown"], make="acme-flow-shakedown")
    assert target is not None and target.name == "acme-flow-shakedown", target


def test_an_unresolvable_resume_names_what_was_asked_for(capsys):
    """The error quotes the argument and the dir searched, not a path the caller never
    typed — after the run-id fallback, printing the last candidate would name a dir that
    was never asked for."""
    _resume_target(["--resume-run", "nope"], make="acme-flow-shakedown")
    err = capsys.readouterr().err
    assert "'nope'" in err and "runs" in err, err


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
