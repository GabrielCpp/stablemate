"""The shared ~/.config/stablemate/config.toml: one file, non-destructive writes.

Standalone + pytest-compatible. Every test redirects the config path, so the
developer's real config is never touched.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from stablemate_core import config as cfgmod  # noqa: E402

_POWER = """\
[power.high.claude]
model = "opus"
effort = "high"

[power.low.claude]
model = "haiku"

[default.claude]
model = "sonnet"
"""


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    return path


# --- the regression that started this ----------------------------------------


def test_writing_a_key_preserves_power_tables(cfg_file):
    """`config set-base` used to stringify [power.*] into a Python repr.

    Nothing errored: resolve_power then saw a str instead of a dict and returned an
    empty mapping, so every node silently fell back to the default model.
    """
    cfg_file.write_text(_POWER)

    cfgmod.write_config_key("base_dir", "/some/path")

    data = tomllib.loads(cfg_file.read_text())
    assert isinstance(data["power"], dict), "power table was stringified"
    assert data["power"]["high"]["claude"] == {"model": "opus", "effort": "high"}
    assert data["default"]["claude"]["model"] == "sonnet"
    assert data["base_dir"] == "/some/path"


def test_power_still_resolves_after_a_write(cfg_file):
    """The user-visible symptom, asserted end to end."""
    cfg_file.write_text(_POWER)
    before = cfgmod.resolve_power("high", "claude")

    cfgmod.write_config_key("library_dir", "/x")
    after = cfgmod.resolve_power("high", "claude")

    assert before == after == cfgmod.PowerMapping(model="opus", effort="high")


def test_repeated_writes_are_stable(cfg_file):
    cfg_file.write_text(_POWER)
    for i in range(5):
        cfgmod.write_config_key("base_dir", f"/p{i}")
    assert cfgmod.resolve_power("low", "claude").model == "haiku"
    assert cfgmod.get_config_value("base_dir") == "/p4"


def test_values_needing_escaping_survive(cfg_file):
    """Hand-rolled escaping is what made the old writer wrong; prove the new one isn't."""
    tricky = '/path/with "quotes" and \\backslash\\ and = signs'
    cfgmod.write_config_key("base_dir", tricky)
    assert cfgmod.get_config_value("base_dir") == tricky


# --- unification + migration -------------------------------------------------


def test_path_is_stablemate_not_workhorse(monkeypatch):
    monkeypatch.delenv(cfgmod.CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    assert cfgmod.config_path().parent.name == "stablemate"


def test_legacy_files_are_read_when_unified_is_absent(tmp_path, monkeypatch):
    """An existing per-tool setup keeps working with no manual migration step."""
    unified = tmp_path / "stablemate" / "config.toml"
    wh = tmp_path / "workhorse" / "config.toml"
    fa = tmp_path / "farrier" / "config.toml"
    wh.parent.mkdir(parents=True)
    fa.parent.mkdir(parents=True)
    wh.write_text(_POWER)
    fa.write_text('library_dir = "/overlay"\nstablemate_dir = "/checkout"\n')

    # Patch the DEFAULT path rather than setting $STABLEMATE_CONFIG: legacy fallback
    # applies only when the path is the default one, so using the env var here would
    # (correctly) suppress the very fallback under test.
    monkeypatch.delenv(cfgmod.CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    monkeypatch.setattr(cfgmod, "config_path", lambda: unified)
    monkeypatch.setattr(cfgmod, "legacy_config_paths", lambda: [wh, fa])

    # workhorse inherits farrier's shared keys — the point of one file.
    assert cfgmod.get_config_value("library_dir") == "/overlay"
    assert cfgmod.resolve_power("high", "claude").model == "opus"


def test_first_write_migrates_legacy_into_the_unified_file(tmp_path, monkeypatch):
    """Otherwise the unified file would exist holding only the new key, and every
    legacy key would be silently dropped on the next read."""
    unified = tmp_path / "stablemate" / "config.toml"
    wh = tmp_path / "workhorse" / "config.toml"
    fa = tmp_path / "farrier" / "config.toml"
    wh.parent.mkdir(parents=True)
    fa.parent.mkdir(parents=True)
    wh.write_text(_POWER)
    fa.write_text('library_dir = "/overlay"\n')

    monkeypatch.delenv(cfgmod.CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    monkeypatch.setattr(cfgmod, "config_path", lambda: unified)
    monkeypatch.setattr(cfgmod, "legacy_config_paths", lambda: [wh, fa])

    cfgmod.write_config_key("base_dir", "/base")

    data = tomllib.loads(unified.read_text())
    assert data["base_dir"] == "/base"
    assert data["library_dir"] == "/overlay"
    assert data["power"]["high"]["claude"]["model"] == "opus"


def test_explicit_path_does_not_fall_back_to_legacy(tmp_path, monkeypatch):
    """Naming a config file means that file — not "and also ~/.config/workhorse".

    Found in a clean-room run: $STABLEMATE_CONFIG pointed at an empty file still
    inherited this machine's real stablemate_dir, so the env var isolated nothing.
    """
    legacy = tmp_path / "workhorse" / "config.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('stablemate_dir = "/leaked"\n')

    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(tmp_path / "does-not-exist.toml"))
    monkeypatch.setattr(cfgmod, "legacy_config_paths", lambda: [legacy])

    assert cfgmod.load_config() == {}
    assert cfgmod.get_config_value("stablemate_dir") is None


def test_unified_file_wins_over_legacy(tmp_path, monkeypatch):
    unified = tmp_path / "stablemate" / "config.toml"
    unified.parent.mkdir(parents=True)
    unified.write_text('library_dir = "/new"\n')
    legacy = tmp_path / "workhorse" / "config.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('library_dir = "/old"\n')

    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(unified))
    monkeypatch.setattr(cfgmod, "legacy_config_paths", lambda: [legacy])

    assert cfgmod.get_config_value("library_dir") == "/new"


def test_legacy_env_var_still_honored(tmp_path, monkeypatch):
    path = tmp_path / "explicit.toml"
    path.write_text('base_dir = "/via-legacy-env"\n')
    monkeypatch.delenv(cfgmod.CONFIG_PATH_ENV, raising=False)
    monkeypatch.setenv(cfgmod.LEGACY_CONFIG_PATH_ENV, str(path))
    assert cfgmod.get_config_value("base_dir") == "/via-legacy-env"


def test_corrupt_config_degrades_to_empty(cfg_file):
    """A broken config must not crash a week-long unattended run."""
    cfg_file.write_text("this is not [ valid toml =")
    assert cfgmod.load_config() == {}
    assert cfgmod.resolve_power("high", "claude") == cfgmod.PowerMapping()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
