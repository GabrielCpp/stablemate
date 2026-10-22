"""`run --workspace NAME`: the env var, the param and the artifacts repo it initialises."""
from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow import Registry

cli_mod = importlib.import_module("workhorse.cli")
run_cmd = importlib.import_module("workhorse.cli.run")


class _StubRegistry(Registry):
    def __init__(self) -> None:
        super().__init__("acme-flow")

    def directory(self) -> Path:
        return Path(__file__).resolve().parent


@pytest.fixture
def home(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(f'[workspaces]\nacme = ["{tmp_path}/api-service", "{tmp_path}/web-app"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))
    monkeypatch.setenv(core_config.WORKSPACE_ENV, "")
    monkeypatch.delenv(core_config.WORKSPACE_ENV)
    launch = tmp_path / "repo"
    launch.mkdir()
    monkeypatch.chdir(launch)
    return tmp_path


def _launch(argv: list[str], monkeypatch) -> tuple[list, str | int | None]:
    seen: list = []

    def fake_run_pyflow(invocation):
        seen.append((invocation, os.environ.get(core_config.WORKSPACE_ENV, "")))
        return 0

    monkeypatch.setattr(run_cmd, "run_pyflow", fake_run_pyflow)
    monkeypatch.setattr(run_cmd, "_load_context_manifest", lambda *a, **k: None)
    with pytest.raises(SystemExit) as excinfo:
        cli_mod.main(argv, workflow="acme-flow", registry=_StubRegistry())
    return seen, excinfo.value.code


def test_a_dry_run_in_a_workspace_exports_it_and_initialises_the_artifacts_repo(home, monkeypatch):
    seen, code = _launch(["run", "--dry-run", "--workspace", "acme"], monkeypatch)

    assert code == 0
    invocation, env_value = seen[0]
    assert invocation.dry_run is True
    assert invocation.params["workspace"] == "acme"
    assert env_value == "acme"
    artifacts = home / "artifacts"
    assert (artifacts / ".git").exists()
    assert (artifacts / ".gitignore").read_text().splitlines() == ["specs/"]
    remotes = subprocess.run(
        ["git", "-C", str(artifacts), "remote"], capture_output=True, text=True, check=True
    )
    assert remotes.stdout.strip() == ""


def test_an_unknown_workspace_exits_naming_the_known_ones(home, monkeypatch, capsys):
    seen, code = _launch(["run", "--workspace", "initech"], monkeypatch)

    assert code == 1 and not seen
    assert "acme" in capsys.readouterr().err
    assert not (home / "artifacts").exists()


def test_a_resume_restores_the_workspace_the_run_recorded(home, monkeypatch):
    run_dir = Path.cwd() / ".agents" / "runs" / "acme-flow-default"
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"engine": "pyflow", "state": "start", "inputs": {"workspace": "acme"}})
    )

    seen, code = _launch(["run", "--resume-run", "default"], monkeypatch)

    assert code == 0
    assert seen[0][1] == "acme"
    assert (home / "artifacts" / ".git").exists()


def test_a_run_without_the_flag_leaves_the_environment_alone(home, monkeypatch):
    seen, _ = _launch(["run"], monkeypatch)

    invocation, env_value = seen[0]
    assert "workspace" not in invocation.params
    assert env_value == ""
    assert not (home / "artifacts").exists()
