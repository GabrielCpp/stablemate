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
from dataclasses import replace
from unittest.mock import patch

from workhorse._vendor.stablemate_core.config import resolve_backend_default, resolve_power
from workhorse.runner import ladder
from workhorse.runner.ladder import _resolve_power_settings

from _fakes import FakeBackend, FakeClock


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


# ── control switch-profile moves a live run onto another set ────────────────

_SWITCHABLE = {
    "profiles": {
        "cheap": {"power": {"high": {"fake": {"model": "haiku"}}}},
        "elsewhere": {"power": {"high": {"claude": {"model": "opus"}}}},
        "bare": {"harness": {"fake": {"env": {"X": "1"}}}},
    }
}


def _runner():
    return ladder.AgentRunner(backend=FakeBackend(None), clock=FakeClock())


def test_a_switch_is_one_assignment_that_the_next_turn_reads():
    """The whole mechanism: the profile is re-narrowed every turn, so moving a run onto
    another model set is a name and nothing else — no reload, no re-exec."""
    runner = _runner()
    with _file(_SWITCHABLE):
        assert ladder.switch_profile(runner, "cheap") == {
            "ok": True, "profile": "cheap", "was": ""
        }
        assert runner.profile.name == "cheap"
        assert _resolve_power_settings("high", "fake", None, runner.profile.name) == (
            "haiku", None
        )


def test_the_box_is_shared_so_a_sub_flow_cannot_put_the_parent_back():
    """The runner is frozen and a handoff copies the env around it, so a *string* here
    could not be reassigned at all — and a per-copy string would put the parent flow back
    on the old model set the moment the child returned. One box is what makes "the run's
    profile" a single fact rather than one per frame."""
    runner = _runner()
    child = replace(runner)  # what a copied frame holds
    with _file(_SWITCHABLE):
        ladder.switch_profile(child, "cheap")
    assert runner.profile.name == "cheap"


def test_an_unknown_profile_is_refused_rather_than_applied():
    """Refused *and said so*: a switch read as landed when it did not would leave a
    week-long run spending on the models nobody chose."""
    runner = _runner()
    with _file(_SWITCHABLE):
        reply = ladder.switch_profile(runner, "nope")
    assert reply["ok"] is False and "nope" in str(reply["error"])
    assert runner.profile.name == ""


def test_a_profile_that_maps_nothing_for_this_runs_backend_is_refused():
    """It would not fail — it would quietly resolve through `[default.<backend>]` to the
    machine's models, which is the substitution profiles exist to prevent."""
    runner = _runner()
    with _file(_SWITCHABLE):
        reply = ladder.switch_profile(runner, "elsewhere")
    assert reply["ok"] is False and "fake" in str(reply["error"])
    assert runner.profile.name == ""


def test_a_profile_carrying_no_models_at_all_is_allowed_through():
    """The check is "has models, but none for this backend". A profile that only sets
    harness environment names no models for anyone, and refusing it would be wrong."""
    runner = _runner()
    with _file(_SWITCHABLE):
        assert ladder.switch_profile(runner, "bare")["ok"] is True


def test_a_run_that_drives_no_agent_is_told_so_rather_than_crashing():
    assert ladder.switch_profile(None, "cheap")["ok"] is False


if __name__ == "__main__":  # parity with the other tests' dual-run style
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all model-resolution tests passed")
