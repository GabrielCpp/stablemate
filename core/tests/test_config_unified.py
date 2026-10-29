"""The shared ~/.config/stablemate/config.toml: one file, non-destructive writes."""

from __future__ import annotations

import os
import sys
import time
import tomllib

import pytest

from stablemate_core import config as cfgmod
from stablemate_core import profiles

_POWER = """\
config_version = 2
default_cli = "claude"

[profiles.claude]
cli = "claude"

[profiles.claude.powers.high]
model = "opus"
effort = "high"

[profiles.claude.powers.low]
model = "haiku"

[profiles.claude.default]
model = "sonnet"
"""


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    return path




def test_writing_a_key_preserves_power_tables(cfg_file):
    """`config set-base` used to stringify [power.*] into a Python repr."""
    cfg_file.write_text(_POWER)

    cfgmod.write_config_key("base_dir", "/some/path")

    data = tomllib.loads(cfg_file.read_text())
    assert isinstance(data["profiles"]["claude"]["powers"], dict), (
        "powers table was stringified"
    )
    assert data["profiles"]["claude"]["powers"]["high"] == {
        "model": "opus",
        "effort": "high",
    }
    assert data["profiles"]["claude"]["default"]["model"] == "sonnet"
    assert data["base_dir"] == "/some/path"


def test_a_write_keeps_comments_and_unknown_keys(cfg_file):
    cfg_file.write_text(
        "config_version = 2\n"
        "# why this checkout\n"
        'stablemate_dir = "/checkout"  # pinned\n'
        "future_option = 7\n"
        "\n[future_table]\nflag = true\n"
    )

    cfgmod.write_config_key("base_dir", "/p")
    cfgmod.write_config_section("saddlebag", {"backend": "keyring"})

    text = cfg_file.read_text()
    data = tomllib.loads(text)
    assert "# why this checkout" in text
    assert "# pinned" in text
    assert data["future_option"] == 7
    assert data["future_table"] == {"flag": True}
    assert data["base_dir"] == "/p"
    assert data["saddlebag"] == {"backend": "keyring"}


def test_a_write_to_a_dotted_section_adds_no_empty_parent_header(cfg_file):
    cfgmod.write_config_section("groom.attend", {"mode": "off"})

    text = cfg_file.read_text()
    assert "[groom.attend]" in text
    assert "[groom]\n" not in text


def test_a_dotted_value_lands_in_its_table_and_loads_back(cfg_file):
    cfgmod.write_config_value("groom.attend.mode", "off")

    assert "[groom.attend]" in cfg_file.read_text()
    groom = cfgmod.load_home_config().groom
    assert groom is not None and groom.attend is not None
    assert groom.attend.mode == "off"


def test_a_dotted_value_the_schema_rejects_is_not_written(cfg_file):
    cfgmod.write_config_key("base_dir", "/p")
    before = cfg_file.read_text()

    with pytest.raises(cfgmod.ConfigError, match="saddlebag.backend"):
        cfgmod.write_config_value("saddlebag.backend", "nope")

    assert cfg_file.read_text() == before


def test_a_dotted_value_the_schema_would_drop_is_not_written(cfg_file):
    cfgmod.write_config_value("profiles.claude", {"cli": "claude"})
    before = cfg_file.read_text()

    with pytest.raises(cfgmod.ConfigError, match="would read it as None"):
        cfgmod.write_config_value("profiles.claude.default.timeout_scale", -1)

    assert cfg_file.read_text() == before


def test_a_write_is_seen_by_the_next_load(cfg_file):
    cfg_file.write_text("config_version = 2\n")
    assert cfgmod.load_home_config().base_dir is None

    cfgmod.write_config_key("base_dir", "/fresh")

    assert cfgmod.load_home_config().base_dir == "/fresh"


def test_power_still_resolves_after_a_write(cfg_file):
    """The user-visible symptom, asserted end to end."""
    cfg_file.write_text(_POWER)
    before = profiles.resolve_power(
        "high", "claude", profiles.select_profile(cfgmod.load_home_config(), "claude")
    )

    cfgmod.write_config_key("library_dir", "/x")
    after = profiles.resolve_power(
        "high", "claude", profiles.select_profile(cfgmod.load_home_config(), "claude")
    )

    assert before == after == profiles.PowerMapping(model="opus", effort="high")


def test_repeated_writes_are_stable(cfg_file):
    cfg_file.write_text(_POWER)
    for i in range(5):
        cfgmod.write_config_key("base_dir", f"/p{i}")
    profile = profiles.select_profile(cfgmod.load_home_config(), "claude")
    assert profiles.resolve_power("low", "claude", profile).model == "haiku"
    assert cfgmod.load_home_config().base_dir == "/p4"


def test_values_needing_escaping_survive(cfg_file):
    """Hand-rolled escaping is what made the old writer wrong; prove the new one isn't."""
    tricky = '/path/with "quotes" and \\backslash\\ and = signs'
    cfgmod.write_config_key("base_dir", tricky)
    assert cfgmod.load_home_config().base_dir == tricky




def test_default_cli_is_the_builtin_when_unset(cfg_file):
    cfg_file.write_text(_POWER)
    assert profiles.resolve_default_cli() == profiles.BUILTIN_DEFAULT_CLI == "claude"


def test_default_cli_is_read_from_the_config(cfg_file):
    cfg_file.write_text('config_version = 2\ndefault_cli = "opencode"\n')
    assert profiles.resolve_default_cli() == "opencode"


def test_default_cli_is_normalized(cfg_file):
    """The consumers lowercase what they read; do it once, here, so they agree."""
    cfg_file.write_text('config_version = 2\ndefault_cli = "  OpenCode  "\n')
    assert profiles.resolve_default_cli() == "opencode"


def test_a_malformed_default_cli_reads_as_unset(cfg_file):
    """Never an exception: this is read on the way into an unattended week-long run, and a config that has gone wrong must degrade to the built-in, not end the run."""
    for bad in (
        "default_cli = 3\n", 'default_cli = ""\n', 'default_cli = "   "\n',
        "default_cli = true\n", 'default_cli = ["opencode"]\n',
    ):
        cfg_file.write_text(f"config_version = 2\n{bad}")
        assert profiles.resolve_default_cli() == "claude", bad


def test_writing_the_default_cli_preserves_the_rest(cfg_file):
    cfg_file.write_text(_POWER)
    cfgmod.write_config_key("default_cli", "opencode")
    data = tomllib.loads(cfg_file.read_text())
    assert data["default_cli"] == "opencode"
    assert data["profiles"]["claude"]["powers"]["high"] == {
        "model": "opus",
        "effort": "high",
    }


def test_default_cli_does_not_bump_the_schema(cfg_file):
    """Additive keys never bump CONFIG_VERSION: an older tool that ignores this one falls back to the same built-in it always used, which is not a wrong answer."""
    cfg_file.write_text('config_version = 2\ndefault_cli = "opencode"\n')
    assert cfgmod.config_version_of(tomllib.loads(cfg_file.read_text())) == 2
    assert cfgmod.check_config_version() == 2




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

    monkeypatch.delenv(cfgmod.CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    monkeypatch.setattr(cfgmod, "config_path", lambda: unified)
    monkeypatch.setattr(cfgmod, "legacy_config_paths", lambda: [wh, fa])

    assert cfgmod.load_home_config().library_dir == "/overlay"
    profile = profiles.select_profile(cfgmod.load_home_config(), "claude")
    assert profiles.resolve_power("high", "claude", profile).model == "opus"


def test_first_write_migrates_legacy_into_the_unified_file(tmp_path, monkeypatch):
    """Otherwise the unified file would exist holding only the new key, and every legacy key would be silently dropped on the next read."""
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
    assert data["profiles"]["claude"]["powers"]["high"]["model"] == "opus"
    assert data["config_version"] == 2


def test_explicit_path_does_not_fall_back_to_legacy(tmp_path, monkeypatch):
    """Naming a config file means that file — not "and also ~/.config/workhorse"."""
    legacy = tmp_path / "workhorse" / "config.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('stablemate_dir = "/leaked"\n')

    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(tmp_path / "does-not-exist.toml"))
    monkeypatch.setattr(cfgmod, "legacy_config_paths", lambda: [legacy])

    assert cfgmod.load_home_config().stablemate_dir is None


def test_unified_file_wins_over_legacy(tmp_path, monkeypatch):
    unified = tmp_path / "stablemate" / "config.toml"
    unified.parent.mkdir(parents=True)
    unified.write_text('library_dir = "/new"\n')
    legacy = tmp_path / "workhorse" / "config.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('library_dir = "/old"\n')

    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(unified))
    monkeypatch.setattr(cfgmod, "legacy_config_paths", lambda: [legacy])

    assert cfgmod.load_home_config().library_dir == "/new"


def test_legacy_env_var_still_honored(tmp_path, monkeypatch):
    path = tmp_path / "explicit.toml"
    path.write_text('base_dir = "/via-legacy-env"\n')
    monkeypatch.delenv(cfgmod.CONFIG_PATH_ENV, raising=False)
    monkeypatch.setenv(cfgmod.LEGACY_CONFIG_PATH_ENV, str(path))
    assert cfgmod.load_home_config().base_dir == "/via-legacy-env"


def test_corrupt_config_raises_on_the_first_load(cfg_file):
    """Nothing good is held yet, so there is no value to fall back on."""
    cfg_file.write_text("this is not [ valid toml =")
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load_home_config()


def test_a_config_that_breaks_mid_run_keeps_the_last_good_value(cfg_file, caplog):
    """A re-read that fails must not crash a week-long unattended run."""
    cfg_file.write_text(_POWER)
    good = cfgmod.load_home_config()

    cfg_file.write_text("this is not [ valid toml =")
    with caplog.at_level("WARNING"):
        kept = cfgmod.load_home_config()

    assert kept is good
    assert "keeping the last good config" in caplog.text


def test_a_bad_type_on_a_re_read_keeps_the_last_good_value_and_names_the_key(
    cfg_file, caplog
):
    cfg_file.write_text(_POWER)
    good = cfgmod.load_home_config()

    cfg_file.write_text(_POWER.replace('model = "haiku"', "model = 3"))
    with caplog.at_level("WARNING"):
        kept = cfgmod.load_home_config()

    assert kept is good
    assert "profiles.claude.powers.low.model" in caplog.text


def test_a_bad_type_on_the_first_load_raises_naming_the_key(cfg_file):
    cfg_file.write_text(_POWER.replace('model = "haiku"', "model = 3"))

    with pytest.raises(cfgmod.ConfigError, match=r"profiles\.claude\.powers\.low\.model"):
        cfgmod.load_home_config()


def test_a_fixed_file_replaces_the_last_good_value(cfg_file):
    cfg_file.write_text(_POWER)
    cfgmod.load_home_config()
    cfg_file.write_text("this is not [ valid toml =")
    cfgmod.load_home_config()

    cfg_file.write_text(_POWER.replace('model = "haiku"', 'model = "fast"') + "# edited\n")

    assert cfgmod.load_home_config().profiles["claude"].powers["low"].model == "fast"


def test_a_rewrite_after_the_guard_with_the_mtime_reset_is_read_again(cfg_file, monkeypatch):
    monkeypatch.setattr(cfgmod, "_RACY_NS", 50_000_000)
    cfg_file.write_text(_POWER)
    stat = cfg_file.stat()
    assert cfgmod.load_home_config().profiles["claude"].powers["low"].model == "haiku"

    time.sleep(0.2)
    cfg_file.write_text(_POWER.replace("haiku", "fast_"))
    os.utime(cfg_file, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert cfgmod.load_home_config().profiles["claude"].powers["low"].model == "fast_"


def test_an_unchanged_file_is_not_read_again(cfg_file, monkeypatch):
    cfg_file.write_text(_POWER)
    old = cfg_file.stat().st_mtime - 60
    os.utime(cfg_file, (old, old))
    first = cfgmod.load_home_config()
    monkeypatch.setattr(
        cfgmod, "_effective_tree", lambda *a, **k: pytest.fail("the file was read again")
    )

    assert cfgmod.load_home_config() is first




@pytest.fixture(autouse=True)
def _reset_warn_cache():
    """The read-warning is once-per-version-per-process; tests must not inherit it."""
    cfgmod._warned_too_new.clear()


def test_writes_stamp_the_schema_version(cfg_file):
    cfgmod.write_config_key("base_dir", "/p")
    data = tomllib.loads(cfg_file.read_text())
    assert data[cfgmod.CONFIG_VERSION_KEY] == cfgmod.CONFIG_VERSION


def test_unversioned_config_is_migrated_in_memory(cfg_file):
    """A v1 file (no `config_version` key, since the key was added with v1) is migrated to v2 in memory on read, so resolvers only need to know the current shape."""
    cfg_file.write_text(_POWER.replace("config_version = 2\n", ""))
    home = cfgmod.load_home_config()
    assert home.profiles["claude"].powers["high"].model == "opus"
    assert home.profiles["claude"].cli == "claude"
    assert cfgmod.config_version_of(tomllib.loads(cfg_file.read_text())) == 1


def test_config_version_of_rejects_a_bool(cfg_file):
    """bool is an int subclass; `config_version = true` must not read as v1."""
    assert cfgmod.config_version_of({cfgmod.CONFIG_VERSION_KEY: True}) == 1


def test_write_refuses_a_newer_config(cfg_file):
    """The load-bearing guard: an old tool must not serialize back a schema it cannot represent, dropping the keys it does not understand — the original bug, exactly."""
    cfg_file.write_text(
        'config_version = 3\n'
        'default_cli = "claude"\n'
        '[profiles.claude]\n'
        'cli = "claude"\n'
        '[profiles.claude.powers.high]\n'
        'model = "opus"\n'
    )

    with pytest.raises(cfgmod.ConfigVersionError) as excinfo:
        cfgmod.write_config_key("base_dir", "/p")

    assert "Refusing to write" in str(excinfo.value)
    data = tomllib.loads(cfg_file.read_text())
    assert "base_dir" not in data
    assert data["profiles"]["claude"]["powers"]["high"]["model"] == "opus"


def test_reads_of_a_newer_config_survive_but_warn(cfg_file, caplog):
    """Reads stay fail-soft: resolve_power re-reads per node, so raising here would kill a week-long run."""
    cfg_file.write_text(
        'config_version = 3\n'
        '[profiles.claude]\n'
        'cli = "claude"\n'
        '[profiles.claude.powers.high]\n'
        'model = "opus"\n'
    )

    with caplog.at_level("WARNING"):
        profile = profiles.select_profile(cfgmod.load_home_config(), "claude")
        assert profiles.resolve_power("high", "claude", profile).model == "opus"

    assert "understands v" in caplog.text


def test_the_read_warning_is_not_repeated(cfg_file, caplog):
    """Per-node re-reads must not bury an unattended run in duplicate warnings."""
    cfg_file.write_text(f"{cfgmod.CONFIG_VERSION_KEY} = {cfgmod.CONFIG_VERSION + 1}\n")
    with caplog.at_level("WARNING"):
        for _ in range(5):
            cfgmod.load_home_config()
    assert caplog.text.count("understands v") == 1


def test_check_config_version_raises_on_a_newer_config(cfg_file):
    """The startup check, for CLIs — where failing is safe and actionable."""
    cfg_file.write_text(f"{cfgmod.CONFIG_VERSION_KEY} = {cfgmod.CONFIG_VERSION + 1}\n")
    with pytest.raises(cfgmod.ConfigVersionError):
        cfgmod.check_config_version()


def test_check_config_version_passes_on_a_current_config(cfg_file):
    cfg_file.write_text(_POWER)
    assert cfgmod.check_config_version() == cfgmod.CONFIG_VERSION


def test_migration_walks_forward_and_backs_the_file_up(cfg_file, monkeypatch):
    """Exercises the walk that bumps CONFIG_VERSION through unknown territory — the mechanism is proven before the release that needs it rather than after."""
    cfg_file.write_text(_POWER.replace("config_version = 2\n", "config_version = 1\n"))

    def v1_to_v2(cfg):
        cfg["migrated_marker"] = "yes"
        return cfg

    monkeypatch.setattr(cfgmod, "CONFIG_VERSION", 2)
    monkeypatch.setattr(cfgmod, "_MIGRATIONS", {1: v1_to_v2})

    cfgmod.write_config_key("base_dir", "/p")

    data = tomllib.loads(cfg_file.read_text())
    assert data[cfgmod.CONFIG_VERSION_KEY] == 2, "the door must close behind a migration"
    assert data["migrated_marker"] == "yes"
    assert data["profiles"]["claude"]["powers"]["high"]["model"] == "opus"

    backup = cfg_file.with_name(cfg_file.name + ".v1.bak")
    assert backup.is_file(), "migration is one-way; the old file must survive"
    assert cfgmod.config_version_of(tomllib.loads(backup.read_text())) == 1


def test_migration_refuses_when_no_step_is_registered(cfg_file, monkeypatch):
    """Better to refuse than to stamp a version the data does not actually match."""
    cfg_file.write_text("config_version = 1\n")
    monkeypatch.setattr(cfgmod, "CONFIG_VERSION", 2)
    monkeypatch.setattr(cfgmod, "_MIGRATIONS", {})

    with pytest.raises(cfgmod.ConfigVersionError, match="no migration registered"):
        cfgmod.write_config_key("base_dir", "/p")




def test_v1_migrates_to_v2_in_memory_on_read(cfg_file):
    """The v1→v2 lift: top-level [power.*] / [default.*] become [profiles.<cli>.*], and [harness.*] becomes [cli.*]."""
    cfg_file.write_text(
        'config_version = 1\n'
        'default_cli = "opencode"\n'
        '\n[power.high.opencode]\n'
        'model = "gpt-5"\n'
        'effort = "high"\n'
        '\n[power.high.claude]\n'
        'model = "opus"\n'
        '\n[default.claude]\n'
        'model = "sonnet"\n'
        '\n[harness.opencode]\n'
        'env = { X = "1" }\n'
    )
    home = cfgmod.load_home_config()
    extra = home.model_extra or {}
    assert "power" not in extra
    assert "harness" not in extra
    assert home.profiles["opencode"].cli == "opencode"
    assert home.profiles["opencode"].powers["high"].model == "gpt-5"
    assert home.profiles["claude"].default is not None
    assert home.profiles["claude"].default.model == "sonnet"
    assert home.cli["opencode"].env == {"X": "1"}


def test_v1_profile_with_default_cli_is_renamed_to_cli(cfg_file):
    cfg_file.write_text(
        'config_version = 1\n'
        '\n[profiles.deepseek]\n'
        'default_cli = "opencode"\n'
        '\n[profiles.deepseek.default.opencode]\n'
        'model = "deep-v4"\n'
    )
    home = cfgmod.load_home_config()
    assert home.profiles["deepseek"].cli == "opencode"
    assert "default_cli" not in (home.profiles["deepseek"].model_extra or {})
    assert home.profiles["deepseek"].default is not None
    assert home.profiles["deepseek"].default.model == "deep-v4"


def test_v1_profile_without_a_cli_is_a_config_error():
    """A v1 profile with no `default_cli` cannot migrate to v2 — its `cli` field is required, and the migration refuses rather than silently dropping the profile (a silent drop is the kind of misconfigured-config data-loss the schema guard exists to prevent)."""
    import tomllib

    v1 = tomllib.loads(
        '[profiles.broken]\n[profiles.broken.power.high.opencode]\nmodel = "x"\n'
    )
    with pytest.raises(cfgmod.ConfigVersionError, match="cli field"):
        cfgmod._migrate_v1_to_v2(v1)




def test_the_home_config_reads_the_qa_tools_table(cfg_file):
    """`[qa_tools.<name>]` is read generically, like `[power.*]` — no dedicated accessor."""
    cfg_file.write_text(
        'config_version = 2\n'
        '[qa_tools.tesseract]\ncommand = "tesseract"\ndescription = "OCR"\n'
        '[qa_tools."ocr-diff"]\ncommand = "/opt/bin/ocr-diff"\n'
    )

    home = cfgmod.load_home_config()

    assert home.qa_tools["tesseract"].command == "tesseract"
    assert home.qa_tools["tesseract"].description == "OCR"
    assert home.qa_tools["ocr-diff"].command == "/opt/bin/ocr-diff"


def test_writing_a_key_preserves_qa_tools_table(cfg_file):
    """The same non-destructive-write guarantee [power.*] gets, for [qa_tools.*]."""
    cfg_file.write_text('config_version = 2\n[qa_tools.tesseract]\ncommand = "tesseract"\n')

    cfgmod.write_config_key("base_dir", "/some/path")

    data = tomllib.loads(cfg_file.read_text())
    assert data["qa_tools"]["tesseract"] == {"command": "tesseract"}
    assert data["base_dir"] == "/some/path"




def test_worktree_dir_is_none_when_unset(cfg_file):
    """Unset means unset — no invented default, or worktrees scatter across the disk."""
    cfg_file.write_text(_POWER)

    assert cfgmod.resolve_worktree_dir() is None


def test_worktree_dir_round_trips_expanded(cfg_file, tmp_path):
    cfgmod.write_worktree_dir(tmp_path / "worktrees")

    assert cfgmod.resolve_worktree_dir() == (tmp_path / "worktrees").resolve()


def test_worktree_dir_survives_a_missing_directory(cfg_file, tmp_path):
    """The path names where worktrees will be created; it need not exist yet."""
    absent = tmp_path / "not-yet" / "worktrees"

    cfgmod.write_worktree_dir(absent)

    assert cfgmod.resolve_worktree_dir() == absent


def test_a_malformed_worktree_dir_reads_as_unset(cfg_file):
    cfg_file.write_text("worktree_dir = 42\n")

    assert cfgmod.resolve_worktree_dir() is None



_SCALED = """\
config_version = 2

[profiles.claude]
cli = "claude"

[profiles.claude.powers.high]
model = "opus"
timeout_scale = 2.5

[profiles.claude.powers.low]
model = "haiku"

[profiles.claude.default]
model = "sonnet"
timeout_scale = 1.5
"""


def test_timeout_scale_parses_from_a_tier_table(cfg_file):
    cfg_file.write_text(_SCALED)
    profile = profiles.select_profile(cfgmod.load_home_config(), "claude")

    assert profiles.resolve_power("high", "claude", profile).timeout_scale == 2.5


def test_timeout_scale_is_none_when_the_tier_omits_it(cfg_file):
    """Unset, not 1.0 — so the caller can still fall through to the profile's default."""
    cfg_file.write_text(_SCALED)
    profile = profiles.select_profile(cfgmod.load_home_config(), "claude")

    assert profiles.resolve_power("low", "claude", profile).timeout_scale is None


def test_timeout_scale_falls_through_to_the_profile_default(cfg_file):
    cfg_file.write_text(_SCALED)
    profile = profiles.select_profile(cfgmod.load_home_config(), "claude")

    assert profiles.resolve_backend_default("claude", profile).timeout_scale == 1.5


def test_timeout_scale_survives_a_write(cfg_file):
    cfg_file.write_text(_SCALED)

    cfgmod.write_config_key("base_dir", "/some/path")

    profile = profiles.select_profile(cfgmod.load_home_config(), "claude")
    assert profiles.resolve_power("high", "claude", profile).timeout_scale == 2.5


def test_an_integer_timeout_scale_reads_as_a_float(cfg_file):
    cfg_file.write_text(
        'config_version = 2\n'
        '[profiles.claude]\ncli = "claude"\n'
        '[profiles.claude.powers.high]\ntimeout_scale = 3\n'
    )
    profile = profiles.select_profile(cfgmod.load_home_config(), "claude")

    assert profiles.resolve_power("high", "claude", profile).timeout_scale == 3.0


@pytest.mark.parametrize("raw", ["\"2.5\"", "true", "0", "-1", "inf", "nan"])
def test_a_malformed_timeout_scale_reads_as_unset(cfg_file, raw):
    """Every rejected value would be worse than the absence it degrades to."""
    cfg_file.write_text(
        f'config_version = 2\n'
        f'[profiles.claude]\ncli = "claude"\n'
        f'[profiles.claude.powers.high]\ntimeout_scale = {raw}\n'
    )
    profile = profiles.select_profile(cfgmod.load_home_config(), "claude")

    assert profiles.resolve_power("high", "claude", profile).timeout_scale is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

def test_artifacts_dir_defaults_under_the_user_data_dir(cfg_file, monkeypatch):
    monkeypatch.delenv(cfgmod.ARTIFACTS_DIR_ENV, raising=False)
    cfg_file.write_text(_POWER)

    resolved = cfgmod.resolve_artifacts_dir()

    assert resolved.name == "artifacts"
    assert resolved.parent.name == "stablemate"


def test_artifacts_dir_reads_the_home_config(cfg_file, tmp_path, monkeypatch):
    monkeypatch.delenv(cfgmod.ARTIFACTS_DIR_ENV, raising=False)
    cfgmod.write_config_key("artifacts_dir", str(tmp_path / "kept"))

    assert cfgmod.resolve_artifacts_dir() == (tmp_path / "kept").resolve()


def test_artifacts_dir_env_beats_the_home_config(cfg_file, tmp_path, monkeypatch):
    cfgmod.write_config_key("artifacts_dir", str(tmp_path / "kept"))
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "from-env"))

    assert cfgmod.resolve_artifacts_dir() == (tmp_path / "from-env").resolve()


def test_a_malformed_artifacts_dir_falls_back_to_the_default(cfg_file, monkeypatch):
    monkeypatch.delenv(cfgmod.ARTIFACTS_DIR_ENV, raising=False)
    cfg_file.write_text("artifacts_dir = 42\n")

    assert cfgmod.resolve_artifacts_dir().name == "artifacts"


def test_paddock_dir_defaults_under_the_user_data_dir(cfg_file):
    cfg_file.write_text(_POWER)

    resolved = cfgmod.resolve_paddock_dir()

    assert resolved.name == "paddock"
    assert resolved.parent.name == "stablemate"


def test_paddock_dir_reads_the_home_config(cfg_file, tmp_path):
    cfgmod.write_config_key("paddock_dir", str(tmp_path / "bench"))

    assert cfgmod.resolve_paddock_dir() == (tmp_path / "bench").resolve()


def test_a_malformed_paddock_dir_falls_back_to_the_default(cfg_file):
    cfg_file.write_text("paddock_dir = 42\n")

    assert cfgmod.resolve_paddock_dir().name == "paddock"


def test_a_version_error_is_caught_as_a_config_error():
    """One `except ConfigError` must cover a config from the future."""
    assert issubclass(cfgmod.ConfigVersionError, cfgmod.ConfigError)
    with pytest.raises(cfgmod.ConfigError):
        raise cfgmod.ConfigVersionError("config_version 99 is newer than this tool")


def test_attend_mode_is_read_in_any_case(cfg_file):
    cfg_file.write_text('config_version = 2\n[groom.attend]\nmode = "Session"\nlast_mode = "HEADLESS"\n')

    groom = cfgmod.load_home_config().groom
    assert groom is not None and groom.attend is not None
    attend = groom.attend

    assert (attend.mode, attend.last_mode) == ("session", "headless")


def test_attend_deny_entries_are_read_as_text(cfg_file):
    cfg_file.write_text('config_version = 2\n[groom.attend]\ndeny = ["merge", 7]\n')

    groom = cfgmod.load_home_config().groom
    assert groom is not None and groom.attend is not None

    assert groom.attend.deny == ["merge", "7"]
