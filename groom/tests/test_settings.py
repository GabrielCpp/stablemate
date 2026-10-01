"""``[groom.attend]``: a nested table a dashboard toggle owns, over an env fallback."""

from __future__ import annotations

import tomllib

import pytest

from groom import settings as groom_settings
from workhorse._vendor.stablemate_core import config as cfgmod

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
    for name in (groom_settings.ATTEND_MODE_ENV, groom_settings.ATTEND_CLI_ENV, groom_settings.ATTEND_DENY_ENV):
        monkeypatch.delenv(name, raising=False)
    return path


def test_writing_the_section_leaves_its_neighbours_intact(cfg_file):
    cfg_file.write_text(_NEIGHBOURS)

    cfgmod.write_config_section(
        groom_settings.ATTEND_SECTION, {"mode": "headless", "deny": ["push a red pr"]}
    )

    data = tomllib.loads(cfg_file.read_text())
    assert data["profiles"]["claude"]["powers"]["high"] == {"model": "opus", "effort": "high"}
    assert data["profiles"]["fast"] == {"cli": "claude"}
    assert data["groom"]["attend"] == {"mode": "headless", "deny": ["push a red pr"]}
    assert data[cfgmod.CONFIG_VERSION_KEY] == cfgmod.CONFIG_VERSION


def test_writing_the_section_replaces_it_rather_than_merging(cfg_file):
    cfgmod.write_config_section(groom_settings.ATTEND_SECTION, {"mode": "off", "deny": ["gone"]})
    cfgmod.write_config_section(groom_settings.ATTEND_SECTION, {"mode": "headless"})

    data = tomllib.loads(cfg_file.read_text())
    assert data["groom"]["attend"] == {"mode": "headless"}


def test_writing_the_section_refuses_a_config_from_the_future(cfg_file):
    cfg_file.write_text(f"{cfgmod.CONFIG_VERSION_KEY} = {cfgmod.CONFIG_VERSION + 1}\n")

    with pytest.raises(cfgmod.ConfigVersionError):
        cfgmod.write_config_section(groom_settings.ATTEND_SECTION, {"mode": "headless"})


def test_nothing_configured_is_off_by_default(cfg_file):
    settings = groom_settings.resolve_attend_settings()

    assert settings.mode == groom_settings.ATTEND_OFF
    assert settings.cli == groom_settings.BUILTIN_ATTEND_CLI
    assert settings.deny == ()
    assert settings.sources["mode"] == groom_settings.DEFAULT_SOURCE


def test_the_environment_is_read_while_the_key_is_absent(cfg_file, monkeypatch):
    monkeypatch.setenv(groom_settings.ATTEND_MODE_ENV, "session")
    monkeypatch.setenv(groom_settings.ATTEND_DENY_ENV, "Push A Red PR, merge conflict")

    settings = groom_settings.resolve_attend_settings()

    assert settings.mode == "session"
    assert settings.sources["mode"] == groom_settings.ENV_SOURCE
    assert settings.deny == ("push a red pr", "merge conflict")
    assert settings.last_mode == "session"


def test_the_config_wins_over_the_environment(cfg_file, monkeypatch):
    monkeypatch.setenv(groom_settings.ATTEND_MODE_ENV, "session")
    cfgmod.write_config_section(groom_settings.ATTEND_SECTION, {"mode": "off"})

    settings = groom_settings.resolve_attend_settings()

    assert settings.mode == groom_settings.ATTEND_OFF
    assert settings.sources["mode"] == groom_settings.CONFIG_SOURCE


def test_an_unknown_mode_falls_back_to_off(cfg_file):
    cfgmod.write_config_section(groom_settings.ATTEND_SECTION, {"mode": "enthusiastic"})

    assert groom_settings.resolve_attend_settings().mode == groom_settings.ATTEND_OFF


def test_last_mode_round_trips_through_a_save(cfg_file):
    groom_settings.write_attend_settings(
        groom_settings.AttendSettings(mode="session", last_mode="session", cli="claude")
    )
    settings = groom_settings.resolve_attend_settings()
    groom_settings.write_attend_settings(
        groom_settings.AttendSettings(
            mode=groom_settings.ATTEND_OFF, last_mode=settings.last_mode, cli=settings.cli
        )
    )

    off = groom_settings.resolve_attend_settings()
    assert off.mode == groom_settings.ATTEND_OFF
    assert off.last_mode == "session"
