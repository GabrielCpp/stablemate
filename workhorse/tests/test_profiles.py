"""Tests for run-level profiles (runner/profiles.py).

Covers discovery, the shipped litellm/litellm-copilot/litellm-claude defaults,
``${VAR}`` interpolation, validation (unknown name, CLI-name collision, bad
default_model), and that a resolved codex model string parses via the existing
``_parse_codex_model``. Runnable two ways:

    ./.venv/bin/python tests/test_profiles.py
    ./.venv/bin/python -m pytest tests/test_profiles.py
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from workhorse.runner import profiles
from workhorse.runner.backends import _parse_codex_model
from workhorse.runner.profiles import DEFAULT_PROFILE, load_profiles, resolve_profile


def _write(text: str) -> str:
    d = Path(tempfile.mkdtemp())
    p = d / "workhorse-profiles.yaml"
    p.write_text(text)
    return str(p)


def _example_file() -> str:
    """The shipped EXAMPLE profiles (under tooling/, NOT embedded in the package)."""
    return str(
        Path(__file__).resolve().parents[1]
        / "tooling"
        / "openrouter-cache"
        / "workhorse-profiles.yaml"
    )


def setup_function(_fn):
    profiles._CACHE.clear()


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    """Keep proxy_local_secret() and user-global discovery out of the real home dir."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


# ── discovery ──────────────────────────────────────────────────────────────────


def test_explicit_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_profiles("/no/such/workhorse-profiles.yaml")


def test_no_profiles_file_is_empty(monkeypatch, tmp_path):
    # The package ships NO embedded default; with nothing discoverable → empty.
    monkeypatch.delenv("AGENT_PROFILES_FILE", raising=False)
    monkeypatch.delenv("AGENT_REPO_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))  # no profiles.yaml under it
    assert load_profiles() == {}


def test_example_file_has_litellm():
    reg = load_profiles(_example_file())
    assert "litellm" in reg
    assert reg["litellm"]["cli"] == "codex"


# ── resolve: default / unknown ───────────────────────────────────────────────────


def test_resolve_none_and_default_return_none():
    assert resolve_profile(None) is None
    assert resolve_profile("") is None
    assert resolve_profile(DEFAULT_PROFILE) is None


def test_unknown_profile_raises():
    with pytest.raises(ValueError) as e:
        resolve_profile("nope")
    assert "nope" in str(e.value)


# ── validation ───────────────────────────────────────────────────────────────────


def test_profile_named_after_cli_rejected():
    path = _write("profiles:\n  codex:\n    cli: codex\n    models: {a: x}\n")
    with pytest.raises(ValueError) as e:
        load_profiles(path)
    assert "claude/codex/copilot" in str(e.value)


def test_bad_default_model_rejected():
    path = _write(
        "profiles:\n  p:\n    cli: codex\n    default_model: nope\n"
        "    models: {mimo: 'mimo@mimo', mimo-pro: 'mimo@mimo-pro'}\n"
    )
    with pytest.raises(ValueError):
        resolve_profile("p", path=path)


def test_single_model_infers_default():
    path = _write("profiles:\n  p:\n    cli: copilot\n    models: {only: only-model}\n")
    prof = resolve_profile("p", path=path)
    assert prof.default_model == "only" and prof.model_for(None) == "only-model"


def test_bad_cli_rejected():
    path = _write("profiles:\n  p:\n    cli: gpt\n    models: {a: x}\n")
    with pytest.raises(ValueError):
        resolve_profile("p", path=path)


# ── shipped litellm profiles ─────────────────────────────────────────────────────


def test_litellm_codex_resolves():
    prof = resolve_profile("litellm", path=_example_file())
    assert prof.cli == "codex"
    assert prof.default_model == "mimo"
    assert prof.model_for(None) == "mimo@mimo"
    assert prof.model_for("mimo-pro") == "mimo@mimo-pro"
    # The managed proxy provides LITELLM_MASTER_KEY — a generated local token, NOT
    # something the operator exports.
    assert prof.env["LITELLM_MASTER_KEY"].startswith("sk-local-")
    assert prof.effort == "none"
    # workhorse owns the proxy lifecycle.
    assert prof.proxy is not None
    assert prof.proxy.port == 4444
    assert prof.proxy.passthrough_env == ("OPENROUTER_API_KEY",)
    assert prof.proxy.start[0] == "docker"
    assert any("compose.litellm.yaml" in a for a in prof.proxy.start)


def test_litellm_codex_model_parses_for_codex():
    prof = resolve_profile("litellm", path=_example_file())
    # The concrete string must split into (codex config profile, LiteLLM model).
    assert _parse_codex_model(prof.model_for("mimo-pro")) == ("mimo", "mimo-pro")


def test_litellm_copilot_byok_env():
    prof = resolve_profile("litellm-copilot", path=_example_file())
    assert prof.cli == "copilot"
    # base URL is workhorse-managed (derived from proxy.port=4444), NOT the ambient env.
    assert prof.env["COPILOT_PROVIDER_BASE_URL"] == "http://localhost:4444/v1"
    assert prof.env["COPILOT_PROVIDER_API_KEY"].startswith("sk-local-")
    assert prof.env["COPILOT_OFFLINE"] == "true"
    assert prof.model_for("mimo-pro") == "mimo-pro"


# ── managed proxy lifecycle ──────────────────────────────────────────────────────


def test_managed_proxy_secret_is_stable():
    # The persisted token is reused across resolves, so an already-running managed
    # proxy matches the token workhorse injects into the CLI.
    a = resolve_profile("litellm", path=_example_file()).env["LITELLM_MASTER_KEY"]
    profiles._CACHE.clear()
    b = resolve_profile("litellm", path=_example_file()).env["LITELLM_MASTER_KEY"]
    assert a == b and a.startswith("sk-local-")


def test_profile_without_proxy_still_requires_env_var():
    # Backward compat: with no proxy block, ${VAR} must come from the environment.
    path = _write(
        "profiles:\n  p:\n    cli: claude\n    models: {m: m}\n"
        "    env: {ANTHROPIC_AUTH_TOKEN: '${SOME_TOKEN}'}\n"
    )
    with pytest.raises(ValueError) as e:
        resolve_profile("p", path=path, environ={})
    assert "SOME_TOKEN" in str(e.value)


# ── ${VAR} interpolation ─────────────────────────────────────────────────────────


def test_env_interpolation_expands(monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    path = _write(
        "profiles:\n  p:\n    cli: claude\n    models: {m: m}\n    env: {X: '${FOO}/v1'}\n"
    )
    assert resolve_profile("p", path=path).env["X"] == "bar/v1"


def test_env_interpolation_missing_var_raises():
    path = _write(
        "profiles:\n  p:\n    cli: claude\n    models: {m: m}\n    env: {X: '${NOPE_UNSET}'}\n"
    )
    # Pass an empty environ so the var is definitely unset.
    with pytest.raises(ValueError) as e:
        resolve_profile("p", path=path, environ={})
    assert "NOPE_UNSET" in str(e.value)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        profiles._CACHE.clear()
        try:
            # __main__ run can't use monkeypatch; set env vars the shipped profiles need.
            os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test")
            os.environ.setdefault("LITELLM_BASE_URL", "http://localhost:4000")
            import inspect

            if "monkeypatch" in inspect.signature(fn).parameters:
                print(f"SKIP  {fn.__name__} (needs pytest monkeypatch)")
                continue
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    raise SystemExit(1 if failed else 0)
