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


# ── --profile: selected, validated, and threaded to the turn ────────────────

_PROFILES = """\
default_cli = "claude"

[profiles.local]
default_cli = "opencode"

[profiles.local.power.high.opencode]
model = "qwen"

[profiles.typo.power.high.openocde]
model = "qwen"

[profiles.cli-only]
default_cli = "codex"
"""


def _run_profiled(argv: list[str], config: Path) -> dict:
    """Drive `run` against a config file, capturing what the invocation carried."""
    captured: dict = {}

    def fake_run_pyflow(invocation):
        captured["profile"] = invocation.config.profile
        captured["backend"] = invocation.config.backend.name
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        launch.mkdir()
        env = {k: v for k, v in os.environ.items() if k != "AGENT_CLI"}
        with patch.dict(os.environ, env, clear=True), patch.object(
            run_cmd, "run_pyflow", fake_run_pyflow
        ), patch.object(run_cmd.Path, "cwd", staticmethod(lambda: launch)):
            _main(["run", "--config", str(config), *argv])
    return captured


def _profiles_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(_PROFILES)
    return path


def test_profile_travels_to_the_run_and_carries_its_default_cli(tmp_path):
    """The profile's `default_cli` is one rung of the CLI ladder, below AGENT_CLI."""
    captured = _run_profiled(["--profile", "local"], _profiles_config(tmp_path))

    assert captured["profile"] == "local"
    assert captured["backend"] == "opencode"


def test_cli_flag_still_wins_over_a_profiles_default(tmp_path):
    """Independent axes: the profile holds the mapping, --cli picks whose entries apply."""
    config = _profiles_config(tmp_path)
    (tmp_path / "both.toml").write_text(
        _PROFILES + '\n[profiles.local.power.high.claude]\nmodel = "opus"\n'
    )
    captured = _run_profiled(["--profile", "local", "--cli", "claude"], tmp_path / "both.toml")

    assert (captured["profile"], captured["backend"]) == ("local", "claude")
    assert config.is_file()


def test_no_profile_leaves_the_top_level_default_cli_in_charge(tmp_path):
    captured = _run_profiled([], _profiles_config(tmp_path))

    assert (captured["profile"], captured["backend"]) == ("", "claude")


def test_an_unknown_profile_is_refused_before_the_first_state(tmp_path, capsys):
    _run_profiled(["--profile", "locl"], _profiles_config(tmp_path))

    err = capsys.readouterr().err
    assert "locl" in err and "local" in err, err


def test_a_misspelled_backend_inside_a_profile_is_refused(tmp_path, capsys):
    """It would otherwise resolve to an empty mapping and spend the run on defaults."""
    _run_profiled(["--profile", "typo", "--cli", "opencode"], _profiles_config(tmp_path))

    err = capsys.readouterr().err
    assert "openocde" in err and "opencode" in err, err


def test_a_profile_with_nothing_for_the_chosen_backend_is_refused(tmp_path, capsys):
    """The easy misuse of two independent axes, and the same silent-default class."""
    _run_profiled(["--profile", "local", "--cli", "claude"], _profiles_config(tmp_path))

    err = capsys.readouterr().err
    assert "'claude'" in err and "local" in err, err


def test_a_profile_that_only_names_a_cli_stays_legal(tmp_path):
    """It claims nothing about models, which is a coherent thing to want."""
    captured = _run_profiled(["--profile", "cli-only"], _profiles_config(tmp_path))

    assert (captured["profile"], captured["backend"]) == ("cli-only", "codex")


def test_the_checks_run_on_a_dry_run_too(tmp_path, capsys):
    """`--dry-run` exists to catch the typo found at hour 30; a profile name is one."""
    _run_profiled(["--profile", "locl", "--dry-run"], _profiles_config(tmp_path))

    assert "locl" in capsys.readouterr().err


# ── --config points the whole process at one config file ────────────────────

def _run_with_config(argv: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        launch = Path(tmp) / "repo"
        launch.mkdir()
        with patch.object(run_cmd, "run_pyflow", lambda invocation: 0), patch.object(
            run_cmd.Path, "cwd", staticmethod(lambda: launch)
        ):
            _main(["run", *argv])


def test_config_flag_is_written_back_to_the_environment(tmp_path):
    """The config is re-read per node and by every subprocess, each through its own
    `config_path()` — so the flag has to move the environment, not just this frame."""
    named = tmp_path / "bench.toml"
    named.write_text('default_cli = "claude"\n')

    with patch.dict(os.environ, {}, clear=False):
        _run_with_config(["--config", str(named)])
        assert os.environ[run_cmd.CONFIG_PATH_ENV] == str(named.resolve())


def test_config_flag_wins_over_the_environment(tmp_path):
    named = tmp_path / "bench.toml"
    named.write_text("")

    with patch.dict(os.environ, {run_cmd.CONFIG_PATH_ENV: "/elsewhere.toml"}):
        _run_with_config(["--config", str(named)])
        assert os.environ[run_cmd.CONFIG_PATH_ENV] == str(named.resolve())


def test_without_the_flag_discovery_is_left_alone(tmp_path):
    """Stamping the *discovered* path would make it explicit — and an explicit path
    suppresses the legacy per-tool merge, so a machine still on the old files would
    silently lose them to a flag nobody passed."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop(run_cmd.CONFIG_PATH_ENV, None)
        _run_with_config([])
        assert run_cmd.CONFIG_PATH_ENV not in os.environ


def test_a_config_that_is_not_there_fails_at_the_boundary(capsys):
    """Read as an empty config instead, the typo costs a week of default models."""
    with patch.dict(os.environ, {}, clear=False):
        _run_with_config(["--config", "/no/such/config.toml"])
    err = capsys.readouterr().err
    assert "--config" in err and "/no/such/config.toml" in err, err


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
