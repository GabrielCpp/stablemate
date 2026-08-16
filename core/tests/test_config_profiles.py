"""`[profiles.<name>]`: a named model set, selected per run.

Standalone + pytest-compatible. The contract under test is *replace, never overlay* —
a selected profile is the whole answer for model selection, and nothing outside it
leaks in.
"""

from __future__ import annotations

import sys

import pytest

from stablemate_core import config as cfgmod

_CFG = """\
default_cli = "claude"

[power.high.claude]
model = "opus"

[power.low.claude]
model = "haiku"

[default.claude]
model = "sonnet"

[harness.opencode]
env = { OPENCODE_DISABLE_AUTOCOMPACT = "1" }

[profiles.local]
default_cli = "opencode"

[profiles.local.power.high.opencode]
model = "qwen/qwen3.6-27b"
effort = "high"

[profiles.local.power.high.default]
model = "big"

[profiles.local.default.opencode]
model = "qwen/qwen3.6-7b"

[profiles.cli-only]
default_cli = "codex"
"""


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(_CFG)
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    return cfgmod.load_config()


# --- narrowing ----------------------------------------------------------------


def test_selected_profile_replaces_the_top_level_tables(cfg):
    profile = cfgmod.select_profile(cfg, "local")

    assert cfgmod.resolve_power("high", "opencode", profile).model == "qwen/qwen3.6-27b"
    # The machine's top-level [power.low.claude] is NOT inherited: a tier the profile
    # does not mention resolves to nothing, not to the operator's global answer.
    assert cfgmod.resolve_power("low", "claude", profile) == cfgmod.PowerMapping()
    assert cfgmod.resolve_backend_default("claude", profile) == cfgmod.PowerMapping()
    assert cfgmod.resolve_backend_default("opencode", profile).model == "qwen/qwen3.6-7b"


def test_the_per_tier_default_fallback_survives_inside_a_profile(cfg):
    """"This tier is the strong model on whatever harness" stays expressible."""
    profile = cfgmod.select_profile(cfg, "local")

    assert cfgmod.resolve_power("high", "codex", profile).model == "big"


def test_harness_env_is_not_part_of_a_profile(cfg):
    """It is a property of the CLI installation, and the one table that merges.

    A profile that silently un-exported a harness knob because it did not restate it
    would be a debugging trap, so it is resolved from the UNNARROWED config.
    """
    assert cfgmod.resolve_harness_env("opencode", cfg) == {
        "OPENCODE_DISABLE_AUTOCOMPACT": "1"
    }
    profile = cfgmod.select_profile(cfg, "local")
    assert cfgmod.resolve_harness_env("opencode", profile) == {}


def test_a_profile_carries_its_own_default_cli(cfg):
    assert cfgmod.resolve_default_cli(cfg) == "claude"
    assert cfgmod.resolve_default_cli(cfgmod.select_profile(cfg, "local")) == "opencode"


def test_no_profile_leaves_the_config_untouched(cfg):
    """The unset selector needs no branch at the call site."""
    assert cfgmod.select_profile(cfg, "") is cfg


# --- what the boundary needs to fail fast -------------------------------------


def test_an_unknown_profile_raises_and_names_the_alternatives(cfg):
    with pytest.raises(cfgmod.UnknownProfileError) as exc:
        cfgmod.select_profile(cfg, "locl")

    message = str(exc.value)
    assert "locl" in message
    assert "local" in message and "cli-only" in message, "the known names must be listed"


def test_an_unknown_profile_raises_when_none_are_defined(tmp_path, monkeypatch):
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(tmp_path / "config.toml"))
    with pytest.raises(cfgmod.UnknownProfileError, match="none defined"):
        cfgmod.select_profile({}, "local")


def test_profile_names_are_reported_sorted(cfg):
    assert cfgmod.profile_names(cfg) == ["cli-only", "local"]


def test_profile_backends_reports_the_names_used_and_validates_none(cfg):
    """core knows no backend registry; workhorse checks these against it."""
    profile = cfgmod.select_profile(cfg, "local")

    assert cfgmod.profile_backends(profile) == ["opencode"]
    assert cfgmod.profile_backends(cfgmod.select_profile(cfg, "cli-only")) == []


def test_profile_backends_reports_a_misspelling_rather_than_hiding_it(cfg):
    profile = {"power": {"high": {"openocde": {"model": "x"}}}}

    assert cfgmod.profile_backends(profile) == ["openocde"]


def test_a_profile_with_no_entries_for_the_backend_is_visible(cfg):
    """`--profile local --cli claude`: the two-axes misuse, caught at the boundary."""
    profile = cfgmod.select_profile(cfg, "local")

    assert cfgmod.profile_has_backend(profile, "opencode")
    # [power.high.default] answers for every backend, so claude resolves after all.
    assert cfgmod.profile_has_backend(profile, "claude")
    assert not cfgmod.profile_has_backend({"power": {"high": {"opencode": {}}}}, "claude")
    # A profile carrying only default_cli stays legal, and has no entries by definition.
    assert not cfgmod.profile_has_backend(cfgmod.select_profile(cfg, "cli-only"), "codex")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
