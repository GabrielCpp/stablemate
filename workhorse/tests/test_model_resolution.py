"""Tests for power-tier model resolution (runner/agent.py:_resolve_power_settings).

A node's ``power:`` is resolved through user-wide config keyed by backend. Missing
config falls through to AGENT_MODEL / AGENT_CLAUDE_MODEL for model and leaves effort
unset so the harness default applies.
Runnable:

    ./.venv/bin/python -m pytest tests/test_model_resolution.py
"""
from __future__ import annotations

from unittest.mock import patch

from workhorse.config import resolve_power
from workhorse.runner.agent import _resolve_power_settings


CONFIG = {
    "power": {
        "high": {
            "claude": {"model": "opus", "effort": "high"},
            "codex": {"model": "@gpt-5.5", "effort": "high"},
            "opencode": {"model": "openai/gpt-5.5", "effort": "high"},
        },
        "medium": {
            "claude": {"model": "sonnet", "effort": "high"},
        },
        "low": {
            "claude": {"model": "haiku", "effort": "high"},
        },
    }
}


def test_none_power_yields_env_model_and_no_effort():
    assert _resolve_power_settings(None, "claude", {}) == (None, None)
    assert _resolve_power_settings(None, "codex", {"AGENT_MODEL": "x"}) == ("x", None)


def test_power_picks_backend_mapping():
    with patch("workhorse.runner.agent.resolve_power") as resolve:
        resolve.side_effect = lambda power, backend: resolve_power(power, backend, CONFIG)
        assert _resolve_power_settings("high", "claude", {}) == ("opus", "high")
        assert _resolve_power_settings("high", "codex", {}) == ("@gpt-5.5", "high")
        assert _resolve_power_settings("high", "opencode", {}) == ("openai/gpt-5.5", "high")


def test_missing_backend_mapping_falls_through_to_env_and_no_effort():
    with patch("workhorse.runner.agent.resolve_power") as resolve:
        resolve.side_effect = lambda power, backend: resolve_power(power, backend, CONFIG)
        assert _resolve_power_settings("medium", "opencode", {}) == (None, None)
        assert _resolve_power_settings("medium", "opencode", {"AGENT_MODEL": "fallback"}) == ("fallback", None)


def test_default_backend_mapping_covers_unlisted_backends():
    cfg = {"power": {"high": {"default": {"model": "default-model", "effort": "high"}}}}
    with patch("workhorse.runner.agent.resolve_power") as resolve:
        resolve.side_effect = lambda power, backend: resolve_power(power, backend, cfg)
        assert _resolve_power_settings("high", "copilot", {}) == ("default-model", "high")


def test_empty_config_keeps_harness_defaults_unset():
    with patch("workhorse.runner.agent.resolve_power") as resolve:
        resolve.side_effect = lambda power, backend: resolve_power(power, backend, {})
        assert _resolve_power_settings("high", "claude", {}) == (None, None)
        assert _resolve_power_settings("high", "claude", {"AGENT_CLAUDE_MODEL": "sonnet"}) == ("sonnet", None)


if __name__ == "__main__":  # parity with the other tests' dual-run style
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all model-resolution tests passed")
