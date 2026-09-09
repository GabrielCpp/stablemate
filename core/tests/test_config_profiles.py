"""`[profiles.<name>]`: a named model set, selected per run.

Standalone + pytest-compatible. The contract under test is *replace, never overlay*:
a selected profile is the whole answer for model selection, and nothing outside it
leaks in. v2 makes the profile per-CLI (each profile carries a ``cli`` field naming
the CLI it runs under), and the auto-select rule finds the profile whose key
matches the resolved CLI.
"""

from __future__ import annotations

import sys

import pytest

from stablemate_core import config as cfgmod

_CFG = """\
config_version = 2
default_cli = "claude"

[cli.opencode]
env = { OPENCODE_DISABLE_AUTOCOMPACT = "1" }

[profiles.opencode]
cli = "opencode"

[profiles.opencode.powers.high]
model = "qwen/qwen3.6-27b"
effort = "high"
timeout_scale = 2.5

[profiles.opencode.powers.low]
model = "qwen/qwen3.6-7b"

[profiles.opencode.default]
model = "qwen/qwen3.6-7b"

[profiles.deepseek]
cli = "opencode"

[profiles.deepseek.default]
model = "openrouter/deepseek-v4-flash-0731"

[profiles.codex-only]
cli = "codex"
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
    profile = cfgmod.select_profile(cfg, "opencode")

    assert cfgmod.resolve_power("high", "opencode", profile).model == "qwen/qwen3.6-27b"
    # A profile is per-CLI, so a power lookup against a different backend returns empty
    # rather than inheriting from anywhere — the profile IS the whole answer.
    assert cfgmod.resolve_power("low", "claude", profile) == cfgmod.PowerMapping()
    assert cfgmod.resolve_backend_default("claude", profile) == cfgmod.PowerMapping()
    assert cfgmod.resolve_backend_default("opencode", profile).model == "qwen/qwen3.6-7b"


def test_timeout_scale_is_resolved_per_profile(cfg):
    """The scale rides the profile, so pinning a slow model pins its clock with it."""
    profile = cfgmod.select_profile(cfg, "opencode")

    assert cfgmod.resolve_power("high", "opencode", profile).timeout_scale == 2.5
    assert cfgmod.resolve_power("high", "claude").timeout_scale is None


def test_a_named_profile_overrides_its_tiers_opencode_keeps_its_own(cfg):
    """Two profiles declaring the same `cli`: the one whose key matches is auto-default;
    the others are accessed via `--profile`. A run that picks `deepseek` sees the
    deepseek model, not the opencode one."""
    profile = cfgmod.select_profile(cfg, "deepseek")

    assert profile.get("cli") == "opencode"
    assert cfgmod.resolve_backend_default("opencode", profile).model == (
        "openrouter/deepseek-v4-flash-0731"
    )
    # The auto-default profile's `powers.high` is not inherited.
    assert cfgmod.resolve_power("high", "opencode", profile) == cfgmod.PowerMapping()


def test_harness_env_is_not_part_of_a_profile(cfg):
    """It is a property of the CLI installation, and the one table that always merges.

    A profile that silently un-exported a harness knob because it did not restate it
    would be a debugging trap, so it is resolved from the UNNARROWED config.
    """
    assert cfgmod.resolve_harness_env("opencode", cfg) == {
        "OPENCODE_DISABLE_AUTOCOMPACT": "1"
    }
    profile = cfgmod.select_profile(cfg, "opencode")
    assert cfgmod.resolve_harness_env("opencode", profile) == {}


def test_a_profile_carries_its_own_cli(cfg):
    """Every profile declares the CLI it runs under — that is what `--profile` selects."""
    assert cfgmod.resolve_default_cli(cfg) == "claude"
    profile = cfgmod.select_profile(cfg, "opencode")
    assert profile.get("cli") == "opencode"


def test_no_profile_returns_empty_for_bare_cli_mode(cfg):
    """`select_profile(cfg, "")` returns {} so the resolvers find no model and the
    workflow emits no --model/--effort flags."""
    assert cfgmod.select_profile(cfg, "") == {}


# --- auto-select --------------------------------------------------------------


def test_auto_select_finds_the_profile_whose_key_matches_the_cli(cfg):
    """The profile named `opencode` (key) declares cli = "opencode" (field); auto-select
    matches on the field and finds it."""
    match = cfgmod.auto_select_profile(cfg, "opencode")

    assert match is not None
    assert match.get("cli") == "opencode"
    assert cfgmod.resolve_power("high", "opencode", match).model == "qwen/qwen3.6-27b"


def test_auto_select_falls_back_to_none_for_an_unknown_cli(cfg):
    """No profile declares cli = "claude" (the top-level default_cli), so auto-select
    finds nothing — bare-CLI mode applies."""
    assert cfgmod.auto_select_profile(cfg, "claude") is None


def test_auto_select_does_not_pick_a_named_profile(cfg):
    """`profiles.deepseek` declares cli = "opencode" but its key is `deepseek`, not
    `opencode`; auto-select for cli = "opencode" picks the key-matched profile."""
    match = cfgmod.auto_select_profile(cfg, "opencode")

    assert match is not None
    assert match is cfgmod.select_profile(cfg, "opencode")


def test_select_active_profile_combines_explicit_and_auto(cfg):
    """`select_active_profile` is the resolver the CLI uses."""
    # explicit name wins
    assert cfgmod.select_active_profile(cfg, name="deepseek").get("cli") == "opencode"
    # auto-pick by cli
    assert cfgmod.select_active_profile(cfg, active_cli="opencode").get("cli") == "opencode"
    # nothing matches → bare-CLI mode → {}
    assert cfgmod.select_active_profile(cfg, active_cli="claude") == {}
    # neither name nor cli → bare-CLI mode
    assert cfgmod.select_active_profile(cfg) == {}


# --- what the boundary needs to fail fast -------------------------------------


def test_an_unknown_profile_raises_and_names_the_alternatives(cfg):
    with pytest.raises(cfgmod.UnknownProfileError) as exc:
        cfgmod.select_profile(cfg, "locl")

    message = str(exc.value)
    assert "locl" in message
    assert "opencode" in message and "deepseek" in message, (
        "the known names must be listed"
    )


def test_an_unknown_profile_raises_when_none_are_defined(tmp_path, monkeypatch):
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(tmp_path / "config.toml"))
    with pytest.raises(cfgmod.UnknownProfileError, match="none defined"):
        cfgmod.select_profile({}, "local")


def test_a_profile_without_a_cli_field_is_rejected(tmp_path, monkeypatch):
    """Every profile must declare its CLI — the resolution rule has nothing to match on
    otherwise."""
    path = tmp_path / "config.toml"
    path.write_text('[profiles.broken]\n[profiles.broken.powers.high]\nmodel = "x"\n')
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))

    with pytest.raises(cfgmod.ConfigError, match="cli field"):
        cfgmod.select_profile(cfgmod.load_config(), "broken")


def test_profile_names_are_reported_sorted(cfg):
    assert cfgmod.profile_names(cfg) == ["codex-only", "deepseek", "opencode"]


def test_profile_backends_reports_the_cli_it_declares(cfg):
    """A profile is for one CLI; ``profile_backends`` returns the one name."""
    profile = cfgmod.select_profile(cfg, "opencode")
    assert cfgmod.profile_backends(profile) == ["opencode"]
    assert cfgmod.profile_backends(cfgmod.select_profile(cfg, "codex-only")) == ["codex"]


def test_profile_backends_reports_a_misspelling_rather_than_hiding_it(cfg):
    """core knows no backend registry; workhorse checks these against it."""
    profile = {"cli": "openocde"}

    assert cfgmod.profile_backends(profile) == ["openocde"]


def test_profile_has_backend_matches_the_cli_field(cfg):
    """A profile is for one CLI; the answer is just ``profile.cli == backend``."""
    profile = cfgmod.select_profile(cfg, "opencode")
    assert cfgmod.profile_has_backend(profile, "opencode")
    assert not cfgmod.profile_has_backend(profile, "claude")

    # A profile declaring only `cli` (no models) is still for its CLI — bare-CLI mode
    # for that profile, which is the meaningful "select this CLI without model overrides"
    # state.
    bare = {"cli": "opencode"}
    assert cfgmod.profile_has_backend(bare, "opencode")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))