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

import io
from contextlib import contextmanager, redirect_stdout
from unittest.mock import patch

from workhorse._vendor.stablemate_core.config import resolve_backend_default, resolve_power
from workhorse.runner import ladder
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
        # Three-arg, because the ladder now hands the resolvers the config it selected:
        # None for "no profile" (this fixture's `cfg`), the narrowed table otherwise.
        power.side_effect = lambda p, b, c=None: resolve_power(p, b, cfg if c is None else c)
        default.side_effect = lambda b, c=None: resolve_backend_default(b, cfg if c is None else c)
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


# ── --profile narrows which config the two resolvers read ───────────────────

_PROFILED = {
    "power": {"high": {"claude": {"model": "opus"}}},
    "default": {"claude": {"model": "sonnet"}},
    "profiles": {
        "local": {
            "power": {"high": {"opencode": {"model": "qwen", "effort": "high"}}},
            "default": {"opencode": {"model": "qwen-small"}},
        }
    },
}


@contextmanager
def _file(cfg):
    """Stand in for the config on disk, which the ladder re-reads every turn."""
    with patch("workhorse.runner.ladder.load_config", lambda: cfg):
        yield


def test_a_profile_replaces_the_top_level_tables():
    with _file(_PROFILED):
        assert _resolve_power_settings("high", "opencode", None, "local") == ("qwen", "high")
        # The machine's [power.high.claude] is not inherited: the profile is the whole
        # answer, so claude resolves to nothing rather than to "opus".
        assert _resolve_power_settings("high", "claude", None, "local") == (None, None)
        assert _resolve_power_settings(None, "opencode", None, "local") == ("qwen-small", None)


def test_without_a_profile_nothing_is_narrowed():
    """No profile hands the resolvers None, i.e. "read the config yourself" — which is
    what every test above exercises, and what keeps the un-profiled path unchanged."""
    with patch("workhorse.runner.ladder.load_config") as load:
        assert ladder._profile_config("") is None
        assert not load.called


def test_a_profile_deleted_mid_run_resolves_empty_rather_than_raising():
    """Fail-soft: a config read must never be what ends a week-long run — and falling
    back to the top level would silently move the run onto the machine's model set."""
    ladder._warned_missing_profile.discard("gone")
    noise = io.StringIO()
    with _file(_PROFILED), redirect_stdout(noise):
        assert _resolve_power_settings("high", "claude", None, "gone") == (None, None)
        # Warned once per name, not once per turn: this runs for every agent node.
        assert _resolve_power_settings("high", "claude", None, "gone") == (None, None)
    assert noise.getvalue().count("gone") == 1, noise.getvalue()


if __name__ == "__main__":  # parity with the other tests' dual-run style
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all model-resolution tests passed")
