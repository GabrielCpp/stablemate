"""Tests for power-tier model resolution (runner/ladder.py:_resolve_power_settings).

A node's ``power:`` is resolved through user-wide config keyed by backend. Missing
config falls through to the run's model override (``AGENT_MODEL`` /
``AGENT_CLAUDE_MODEL``, resolved once into ``RunConfig`` at the CLI boundary and
passed in here), then to the per-backend ``[default.<backend>]`` config table; effort
falls through to that table directly. Anything still unset stays None so the harness
default applies.
Runnable:

    ./.venv/bin/python -m pytest tests/test_model_resolution.py
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from stablemate_core.config import resolve_backend_default, resolve_power
from workhorse.runner.ladder import _resolve_power_settings


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


@contextmanager
def _config(cfg):
    """Route both config lookups in the ladder module at ``cfg`` (never the real file)."""
    with (
        patch("workhorse.runner.ladder.resolve_power") as power,
        patch("workhorse.runner.ladder.resolve_backend_default") as default,
    ):
        power.side_effect = lambda p, b: resolve_power(p, b, cfg)
        default.side_effect = lambda b: resolve_backend_default(b, cfg)
        yield


def test_none_power_yields_the_override_model_and_no_effort():
    with _config(CONFIG):
        assert _resolve_power_settings(None, "claude", None) == (None, None)
        assert _resolve_power_settings(None, "codex", "x") == ("x", None)


def test_power_picks_backend_mapping():
    with _config(CONFIG):
        assert _resolve_power_settings("high", "claude", None) == ("opus", "high")
        assert _resolve_power_settings("high", "codex", None) == ("@gpt-5.5", "high")
        assert _resolve_power_settings("high", "opencode", None) == ("openai/gpt-5.5", "high")


def test_missing_backend_mapping_falls_through_to_the_override_and_no_effort():
    with _config(CONFIG):
        assert _resolve_power_settings("medium", "opencode", None) == (None, None)
        assert _resolve_power_settings("medium", "opencode", "fallback") == ("fallback", None)


def test_default_backend_mapping_covers_unlisted_backends():
    cfg = {"power": {"high": {"default": {"model": "default-model", "effort": "high"}}}}
    with _config(cfg):
        assert _resolve_power_settings("high", "copilot", None) == ("default-model", "high")


def test_empty_config_keeps_harness_defaults_unset():
    with _config({}):
        assert _resolve_power_settings("high", "claude", None) == (None, None)
        assert _resolve_power_settings("high", "claude", "sonnet") == ("sonnet", None)


def test_backend_default_fills_powerless_node():
    cfg = {"default": {"opencode": {"model": "openai/gpt-5.5", "effort": "high"}}}
    with _config(cfg):
        assert _resolve_power_settings(None, "opencode", None) == ("openai/gpt-5.5", "high")
        # Only the named backend gets the default — others stay on harness defaults.
        assert _resolve_power_settings(None, "claude", None) == (None, None)


def test_power_mapping_wins_over_backend_default():
    cfg = dict(CONFIG, default={"opencode": {"model": "wrong", "effort": "low"}})
    with _config(cfg):
        assert _resolve_power_settings("high", "opencode", None) == ("openai/gpt-5.5", "high")


def test_override_model_wins_over_backend_default():
    cfg = {"default": {"opencode": {"model": "config-default"}}}
    with _config(cfg):
        assert _resolve_power_settings(None, "opencode", "run-override") == ("run-override", None)


def test_backend_default_fills_fields_power_left_unset():
    # The power tier names a model but no effort; effort falls to the default table.
    cfg = {
        "power": {"medium": {"opencode": {"model": "openai/gpt-5.5"}}},
        "default": {"opencode": {"model": "unused", "effort": "high"}},
    }
    with _config(cfg):
        assert _resolve_power_settings("medium", "opencode", None) == ("openai/gpt-5.5", "high")


def test_resolve_backend_default_ignores_malformed_tables():
    assert resolve_backend_default("opencode", {}) == resolve_backend_default("opencode", {"default": "nope"})
    assert resolve_backend_default("opencode", {"default": {"opencode": "nope"}}).model is None
    assert resolve_backend_default("opencode", {"default": {"opencode": {"model": ""}}}).model is None


if __name__ == "__main__":  # parity with the other tests' dual-run style
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all model-resolution tests passed")
