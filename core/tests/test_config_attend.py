"""``[groom.attend]``: a nested table a dashboard toggle owns, over an env fallback.

The two things that can go wrong here are both silent. A section write that flattens
its neighbours takes out ``[power.*]`` exactly the way the string-formatting write once
did; and a config value that quietly loses to an environment variable makes the toggle
lie about what the fleet is doing.
"""

from __future__ import annotations

import tomllib

import pytest

from stablemate_core import config as cfgmod

_NEIGHBOURS = """\
config_version = 2

[profiles.claude]
cli = "claude"

[profiles.claude.powers.high]
model = "opus"
effort = "high"

[profiles.fast]
cli = "claude"
"""


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    for name in (cfgmod.ATTEND_MODE_ENV, cfgmod.ATTEND_CLI_ENV, cfgmod.ATTEND_DENY_ENV):
        monkeypatch.delenv(name, raising=False)
    return path


def test_writing_the_section_leaves_its_neighbours_intact(cfg_file):
    cfg_file.write_text(_NEIGHBOURS)

    cfgmod.write_config_section(
        cfgmod.ATTEND_SECTION, {"mode": "headless", "deny": ["push a red pr"]}
    )

    data = tomllib.loads(cfg_file.read_text())
    assert data["profiles"]["claude"]["powers"]["high"] == {"model": "opus", "effort": "high"}
    assert data["profiles"]["fast"] == {"cli": "claude"}
    assert data["groom"]["attend"] == {"mode": "headless", "deny": ["push a red pr"]}
    assert data[cfgmod.CONFIG_VERSION_KEY] == cfgmod.CONFIG_VERSION


def test_writing_the_section_replaces_it_rather_than_merging(cfg_file):
    cfgmod.write_config_section(cfgmod.ATTEND_SECTION, {"mode": "off", "deny": ["gone"]})
    cfgmod.write_config_section(cfgmod.ATTEND_SECTION, {"mode": "headless"})

    data = tomllib.loads(cfg_file.read_text())
    assert data["groom"]["attend"] == {"mode": "headless"}


def test_writing_the_section_refuses_a_config_from_the_future(cfg_file):
    cfg_file.write_text(f"{cfgmod.CONFIG_VERSION_KEY} = {cfgmod.CONFIG_VERSION + 1}\n")

    with pytest.raises(cfgmod.ConfigVersionError):
        cfgmod.write_config_section(cfgmod.ATTEND_SECTION, {"mode": "headless"})


def test_nothing_configured_is_off_by_default(cfg_file):
    settings = cfgmod.resolve_attend_settings()

    assert settings.mode == cfgmod.ATTEND_OFF
    assert settings.cli == cfgmod.BUILTIN_ATTEND_CLI
    assert settings.deny == ()
    assert settings.sources["mode"] == cfgmod.DEFAULT_SOURCE


def test_the_environment_is_read_while_the_key_is_absent(cfg_file, monkeypatch):
    monkeypatch.setenv(cfgmod.ATTEND_MODE_ENV, "session")
    monkeypatch.setenv(cfgmod.ATTEND_DENY_ENV, "Push A Red PR, merge conflict")

    settings = cfgmod.resolve_attend_settings()

    assert settings.mode == "session"
    assert settings.sources["mode"] == cfgmod.ENV_SOURCE
    assert settings.deny == ("push a red pr", "merge conflict")
    # A running-but-unconfigured mode is what the toggle should restore.
    assert settings.last_mode == "session"


def test_the_config_wins_over_the_environment(cfg_file, monkeypatch):
    monkeypatch.setenv(cfgmod.ATTEND_MODE_ENV, "session")
    cfgmod.write_config_section(cfgmod.ATTEND_SECTION, {"mode": "off"})

    settings = cfgmod.resolve_attend_settings()

    assert settings.mode == cfgmod.ATTEND_OFF
    assert settings.sources["mode"] == cfgmod.CONFIG_SOURCE


def test_an_unknown_mode_falls_back_to_off(cfg_file):
    cfgmod.write_config_section(cfgmod.ATTEND_SECTION, {"mode": "enthusiastic"})

    assert cfgmod.resolve_attend_settings().mode == cfgmod.ATTEND_OFF


def test_last_mode_round_trips_through_a_save(cfg_file):
    cfgmod.write_attend_settings(
        cfgmod.AttendSettings(mode="session", last_mode="session", cli="claude")
    )
    settings = cfgmod.resolve_attend_settings()
    cfgmod.write_attend_settings(
        cfgmod.AttendSettings(
            mode=cfgmod.ATTEND_OFF, last_mode=settings.last_mode, cli=settings.cli
        )
    )

    off = cfgmod.resolve_attend_settings()
    assert off.mode == cfgmod.ATTEND_OFF
    assert off.last_mode == "session"
