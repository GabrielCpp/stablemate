"""What `run` decides around the workflow it was handed.

*Which* workflow is not among them — the console script is the workflow's own and hands
its registry in. What is left for the CLI to decide, and what these cover, is everything
*around* it, which is the CLI's contract rather than the driver's:

  * `--runs-dir` defaults to <cwd>/.agents/runs — deduced from the launch dir, not from
    wherever the workflow package happens to be installed;
  * `AGENT_REPO_DIR` defaults to the launch cwd for the same reason, and an explicit
    value wins;
  * `--resume-run` accepts every spelling that names a run, including the `--run-id`
    that made it.
"""
from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from workhorse.pyflow import Registry

cli_mod = importlib.import_module("workhorse.cli")
run_cmd = importlib.import_module("workhorse.cli.run")


class _StubRegistry(Registry):
    """Stands in for the bound Registry — the CLI only passes it through.

    A real `Registry` rather than a look-alike: the CLI's parameter is the type, and
    only the entry point (which these tests never reach) is stubbed out.
    """

    def __init__(self) -> None:
        super().__init__('acme-flow')

    def directory(self) -> Path:
        return Path(__file__).resolve().parent


def _main(argv: list[str]) -> None:
    """Drive the console script the way one of a workflow's own would."""
    try:
        cli_mod.main(argv, workflow="acme-flow", registry=_StubRegistry())
    except SystemExit:
        pass


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
            run_cmd.Path, "cwd", staticmethod(lambda: launch)
        ):
            _main(["run"])
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
        ), patch.object(run_cmd.Path, "cwd", staticmethod(lambda: launch)):
            _main(["run"])
            assert os.environ["AGENT_REPO_DIR"] == str(launch.resolve())


def test_agent_repo_dir_respects_explicit_value():
    # An explicitly-set AGENT_REPO_DIR (e.g. from the farrier Makefile) wins.
    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        launch.mkdir()
        with patch.dict(os.environ, {"AGENT_REPO_DIR": "/pinned/repo"}, clear=False), \
                patch.object(run_cmd, "run_pyflow", lambda invocation: 0), patch.object(
                    run_cmd.Path, "cwd", staticmethod(lambda: launch)
                ):
            _main(["run"])
            assert os.environ["AGENT_REPO_DIR"] == "/pinned/repo"


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
            run_cmd.Path, "cwd", staticmethod(lambda: launch)
        ):
            _main(["run", *argv])
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
