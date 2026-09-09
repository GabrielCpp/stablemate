"""Tests for power-tier model resolution (runner/ladder.py:_resolve_power_settings).

A node's ``power:`` is resolved through the active profile's `powers.<tier>` table.
Missing entries fall through to the profile's `default`, then to the run's model
override (``AGENT_MODEL`` / ``AGENT_CLAUDE_MODEL``, resolved once into ``RunConfig``
at the CLI boundary and passed in here); effort falls through to the profile's
`default` directly (it has no override). Anything still unset stays None so the
harness default applies.

Profiles are v2-shaped: a narrowed profile table the resolver reads as `powers.<tier>`
flat (no per-backend nesting — the profile itself is per-CLI). The fixtures here are
already narrowed, since the ladder hands the resolver the narrowed table rather
than the full config.

Runnable:

    ./.venv/bin/python -m pytest tests/test_model_resolution.py
"""
from __future__ import annotations

import io
from contextlib import contextmanager, redirect_stdout
from unittest.mock import patch

from workhorse._vendor.stablemate_core.config import resolve_backend_default, resolve_power
from workhorse import otel
from workhorse.runner import ladder
from workhorse.runner.ladder import _resolve_power_settings

from _fakes import FakeBackend, FakeClock, RecordingTelemetry


# An already-narrowed profile. Resolvers read profile.powers.<tier> flat, profile.default.
CONFIG = {
    "cli": "claude",
    "powers": {
        "high": {"model": "opus", "effort": "high"},
        "medium": {"model": "sonnet", "effort": "high"},
        "low": {"model": "haiku", "effort": "high"},
    },
    "default": {"model": "sonnet", "effort": "medium"},
}


@contextmanager
def _config(cfg):
    """Route both config lookups in the ladder module at ``cfg`` (never the real file)."""
    with (
        patch("workhorse.runner.ladder.resolve_power") as power,
        patch("workhorse.runner.ladder.resolve_backend_default") as default,
    ):
        power.side_effect = lambda p, b, c=None: resolve_power(p, b, cfg if c is None else c)
        default.side_effect = lambda b, c=None: resolve_backend_default(b, cfg if c is None else c)
        yield


def _model_effort(*args):
    """The resolved (model, effort), dropping the third member of the triple.

    ``_resolve_power_settings`` also returns the tier's wall-clock ``timeout_scale``,
    which has no observable effect until the ladder multiplies a budget by it — so it
    is asserted in ``tests/test_node_timeout.py``, where that effect exists, and left
    out of the resolution assertions here.
    """
    return _resolve_power_settings(*args)[:2]


def test_none_power_yields_the_profile_default_and_no_override():
    """No `power:` set on the node: the profile's `default` table provides model +
    effort. A run-level model override still wins over the default."""
    with _config(CONFIG):
        assert _model_effort(None, "claude", None) == ("sonnet", "medium")
        assert _model_effort(None, "claude", "x") == ("x", "medium")


def test_power_picks_the_tier_table():
    """Each tier is a flat mapping — model + effort per the profile's powers.<tier>."""
    with _config(CONFIG):
        assert _model_effort("high", "claude", None) == ("opus", "high")
        assert _model_effort("medium", "claude", None) == ("sonnet", "high")
        assert _model_effort("low", "claude", None) == ("haiku", "high")


def test_a_backend_mismatch_returns_empty():
    """The resolver validates the narrowed profile's `cli` against the requested
    backend: an opencode-profile call against claude returns nothing rather than
    silently billing on the wrong CLI."""
    with _config(CONFIG):
        assert _model_effort("medium", "opencode", None) == (None, None)
        assert _model_effort("medium", "opencode", "fallback") == ("fallback", None)


def test_empty_config_keeps_harness_defaults_unset():
    """A bare-CLI run (empty cfg handed to the resolver) reads nothing — the CLI's
    own default model applies, and effort is whatever the CLI's invocation defaults
    to."""
    with _config({}):
        assert _model_effort("high", "claude", None) == (None, None)
        assert _model_effort("high", "claude", "sonnet") == ("sonnet", None)


def test_default_table_fills_powerless_node():
    """A node with no `power:` reads the profile's `default` table — the per-CLI
    fallback model/effort, which every backend implements."""
    with _config(CONFIG):
        assert _model_effort(None, "claude", None) == ("sonnet", "medium")
        # Only the profile's own CLI matches.
        assert _model_effort(None, "opencode", None) == (None, None)


def test_default_table_fills_fields_power_left_unset():
    """A power tier names a model but no effort; effort falls to the default table."""
    cfg = {
        "cli": "claude",
        "powers": {"medium": {"model": "sonnet"}},
        "default": {"model": "sonnet", "effort": "high"},
    }
    with _config(cfg):
        assert _model_effort("medium", "claude", None) == ("sonnet", "high")


def test_resolve_backend_default_ignores_malformed_tables():
    """Defensive: malformed `default` shapes degrade to empty, never raise."""
    assert resolve_backend_default("claude", {}) == resolve_backend_default(
        "claude", {}
    )
    assert resolve_backend_default("claude", {"default": "nope"}).model is None
    assert resolve_backend_default("claude", {"default": {"model": ""}}).model is None
    # A profile whose cli doesn't match the requested backend returns empty.
    assert resolve_backend_default("opencode", {"cli": "claude", "default": {"model": "x"}}).model is None


# ── --profile narrows which config the two resolvers read ───────────────────

# A full v2 config — top level — used for the file-reading tests. The fixture below
# narrows by name to exercise the profile-resolving path.
_NARROWABLE = {
    "profiles": {
        "local": {
            "cli": "opencode",
            "powers": {"high": {"model": "qwen", "effort": "high"}},
            "default": {"model": "qwen-small"},
        },
        "opencode": {
            "cli": "opencode",
            "default": {"model": "opencode-default"},
        },
    }
}


@contextmanager
def _file(cfg):
    """Stand in for the config on disk, which the ladder re-reads every turn."""
    with patch("workhorse.runner.ladder.load_config", lambda: cfg):
        yield


def test_a_profile_replaces_the_top_level_tables():
    """When `--profile local` is set, the resolvers see only the local profile — its
    `powers.high` answers for opencode, nothing else does."""
    with _file(_NARROWABLE):
        assert _model_effort("high", "opencode", None, "local") == ("qwen", "high")
        # The profile is for opencode, so a claude call returns nothing — the profile
        # IS the whole answer, not a fragment.
        assert _model_effort("high", "claude", None, "local") == (None, None)
        assert _model_effort(None, "opencode", None, "local") == ("qwen-small", None)


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
    with _file(_NARROWABLE), redirect_stdout(noise):
        assert _model_effort("high", "claude", None, "gone") == (None, None)
        # Warned once per name, not once per turn: this runs for every agent node.
        assert _model_effort("high", "claude", None, "gone") == (None, None)
    assert noise.getvalue().count("gone") == 1, noise.getvalue()


# ── control switch-profile moves a live run onto another set ────────────────

_SWITCHABLE = {
    "profiles": {
        "cheap": {"cli": "fake", "powers": {"high": {"model": "haiku"}}},
        "elsewhere": {"cli": "claude", "powers": {"high": {"model": "opus"}}},
        "bare": {"cli": "fake"},  # CLI only, no models
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
        assert _model_effort("high", "fake", None, runner.profile.name) == (
            "haiku", None
        )


def test_a_switch_re_stamps_the_run_span_so_telemetry_says_what_it_spent_on():
    """The root span closes with the run, so a switch at hour two of a hundred is not a
    lost update — it is the correction that keeps a cross-run comparison honest."""
    runner = _runner()
    fake = RecordingTelemetry()
    previous = otel.install(otel.TelemetryHost(active=fake))
    try:
        with _file(_SWITCHABLE):
            ladder.switch_profile(runner, "cheap")
            # A refusal changes no models, so it must leave the attribute alone too.
            ladder.switch_profile(runner, "nosuch")
    finally:
        otel.install(previous)

    assert fake.run_attributes == [("workhorse.profile", "cheap")]


def test_the_box_is_shared_so_a_sub_flow_cannot_put_the_parent_back():
    """The runner is frozen and a handoff copies the env around it, so a *string* here
    could not be reassigned at all — and a per-copy string would put the parent flow back
    on the old model set the moment the child returned. One box is what makes "the run's
    profile" a single fact rather than one per frame."""
    runner = _runner()
    child = runner  # what a copied frame holds (frozen dataclass: same box for profile)
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
    """It would not fail — it would quietly resolve through the opencode-profile's
    `default` to the wrong models, which is the substitution profiles exist to
    prevent."""
    runner = _runner()
    with _file(_SWITCHABLE):
        reply = ladder.switch_profile(runner, "elsewhere")
    assert reply["ok"] is False and "fake" in str(reply["error"])
    assert runner.profile.name == ""


def test_a_profile_carrying_no_models_at_all_is_allowed_through():
    """The check is "has models, but none for this backend". A profile that only sets
    `cli` and no models stays legal — bare-CLI mode for that profile."""
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