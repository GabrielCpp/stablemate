"""Tests for the --profile / --cli wiring in main._run_run.

Verifies a named profile pins AGENT_CLI, injects its env, and runs (with the proxy
health-check stubbed); that --cli and --profile collide; that an unknown profile and
an unreachable proxy each exit 1. Runnable:

    ./.venv/bin/python -m pytest tests/test_main_profile.py
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pytest

import importlib

from workhorse.runner import profiles

# workhorse/__init__.py does `from .main import main`, shadowing the submodule
# attribute with the function — so import the module object explicitly.
main = importlib.import_module("workhorse.main")

# The example profiles ship under tooling/, not embedded in the package.
EXAMPLE = str(
    Path(__file__).resolve().parents[1]
    / "tooling" / "openrouter-cache" / "workhorse-profiles.yaml"
)


def _args(**over) -> argparse.Namespace:
    base = dict(
        workflow=None, cli=None, profile=None, profiles_file=None, runs_dir=None,
        run_id=None, params=None, params_file=None, context_file=None,
        resume_run=None, resume_latest=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


@pytest.fixture
def workflow_file() -> str:
    p = Path(tempfile.mkdtemp()) / "workflow.yaml"
    p.write_text("name: t\nstart: a\nnodes: []\n")
    return str(p)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    # _run_run mutates os.environ DIRECTLY (not via monkeypatch), and
    # monkeypatch.delenv(raising=False) does NOT register a restore when the key was
    # absent — so snapshot/restore these keys by hand to avoid leaking AGENT_PROFILE
    # into later tests (e.g. test_node_timeout's run_agent).
    import os
    keys = ("AGENT_CLI", "AGENT_PROFILE", "AGENT_PROFILES_FILE")
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    # The upstream key the managed proxy passes through (passthrough_env).
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    # Keep the managed proxy secret out of the real home dir.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    profiles._CACHE.clear()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    profiles._CACHE.clear()


def test_profile_activates_cli_env_and_runs(workflow_file, monkeypatch):
    captured = {}
    # Proxy already up → no start; env injected, run proceeds.
    monkeypatch.setattr(main, "_check_proxy_reachable", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: pytest.fail("should not start an up proxy"))
    monkeypatch.setattr(main, "run", lambda *a, **k: (captured.update(ran=True), 0)[1])

    with pytest.raises(SystemExit) as e:
        main._run_run(_args(workflow=workflow_file, profile="litellm", profiles_file=EXAMPLE))

    assert e.value.code == 0
    assert captured.get("ran") is True
    import os
    assert os.environ["AGENT_CLI"] == "codex"        # pinned from the profile
    assert os.environ["AGENT_PROFILE"] == "litellm"
    # The managed proxy token is injected for the CLI subprocess to inherit.
    assert os.environ["LITELLM_MASTER_KEY"].startswith("sk-local-")


def test_proxy_down_is_started(workflow_file, monkeypatch):
    # Down on first probe → workhorse runs proxy.start, then it becomes ready.
    probes = iter([(False, "refused"), (True, "ok")])
    monkeypatch.setattr(main, "_check_proxy_reachable", lambda *a, **k: next(probes, (True, "ok")))
    started = {}
    def _fake_run(cmd, **kw):
        started["cmd"] = cmd
        started["env"] = kw.get("env", {})
        import subprocess as sp
        return sp.CompletedProcess(cmd, 0)
    monkeypatch.setattr(main.subprocess, "run", _fake_run)
    monkeypatch.setattr(main, "run", lambda *a, **k: 0)

    with pytest.raises(SystemExit) as e:
        main._run_run(_args(workflow=workflow_file, profile="litellm", profiles_file=EXAMPLE))

    assert e.value.code == 0
    assert started["cmd"][0] == "docker"                       # proxy.start ran
    assert started["env"]["LITELLM_PORT"] == "4444"            # managed port passed
    assert started["env"]["LITELLM_MASTER_KEY"].startswith("sk-local-")
    assert started["env"]["OPENROUTER_API_KEY"] == "sk-or-test"  # upstream key passed through


def test_proxy_start_failure_exits_1(workflow_file, monkeypatch):
    import subprocess as sp
    monkeypatch.setattr(main, "_check_proxy_reachable", lambda *a, **k: (False, "refused"))
    def _boom(cmd, **kw):
        raise sp.CalledProcessError(1, cmd)
    monkeypatch.setattr(main.subprocess, "run", _boom)
    with pytest.raises(SystemExit) as e:
        main._run_run(_args(workflow=workflow_file, profile="litellm", profiles_file=EXAMPLE))
    assert e.value.code == 1


def test_proxy_missing_upstream_key_exits_1(workflow_file, monkeypatch):
    # passthrough_env (OPENROUTER_API_KEY) absent → fail fast before starting.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: pytest.fail("must not start without upstream key"))
    with pytest.raises(SystemExit) as e:
        main._run_run(_args(workflow=workflow_file, profile="litellm", profiles_file=EXAMPLE))
    assert e.value.code == 1


def test_cli_and_profile_mutually_exclusive(workflow_file):
    with pytest.raises(SystemExit) as e:
        main._run_run(_args(workflow=workflow_file, cli="codex", profile="litellm"))
    assert e.value.code == 1


def test_unknown_profile_exits_1(workflow_file, monkeypatch):
    monkeypatch.setattr(main, "_check_proxy_reachable", lambda *a, **k: (True, "ok"))
    with pytest.raises(SystemExit) as e:
        main._run_run(_args(workflow=workflow_file, profile="does-not-exist"))
    assert e.value.code == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
