"""The shared ~/.config/stablemate/config.toml: one file, non-destructive writes.

Standalone + pytest-compatible. Every test redirects the config path, so the
developer's real config is never touched.

Tests here assert the load / write / version machinery on the **v2 schema** —
``[profiles.<cli>].powers.<tier>``, ``[profiles.<cli>].default``, ``[cli.<cli>].env``.
The v1→v2 migration is exercised by ``test_v1_migrates_to_v2_in_memory_on_read``.
"""

from __future__ import annotations

import sys
import tomllib

import pytest

from stablemate_core import config as cfgmod

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


# --- the regression that started this ----------------------------------------


def test_writing_a_key_preserves_power_tables(cfg_file):
    """`config set-base` used to stringify [power.*] into a Python repr.

    Nothing errored: resolve_power then saw a str instead of a dict and returned an
    empty mapping, so every node silently fell back to the default model.
    """
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


def test_power_still_resolves_after_a_write(cfg_file):
    """The user-visible symptom, asserted end to end.

    Under v2 the resolver needs a narrowed profile to find a power table — the full
    un-narrowed config carries no top-level model tables, so calling without a
    profile would always return empty. This test selects the claude profile both
    times to exercise the write path.
    """
    cfg_file.write_text(_POWER)
    before = cfgmod.resolve_power(
        "high", "claude", cfgmod.select_profile(cfgmod.load_config(), "claude")
    )

    cfgmod.write_config_key("library_dir", "/x")
    after = cfgmod.resolve_power(
        "high", "claude", cfgmod.select_profile(cfgmod.load_config(), "claude")
    )

    assert before == after == cfgmod.PowerMapping(model="opus", effort="high")


def test_repeated_writes_are_stable(cfg_file):
    cfg_file.write_text(_POWER)
    for i in range(5):
        cfgmod.write_config_key("base_dir", f"/p{i}")
    profile = cfgmod.select_profile(cfgmod.load_config(), "claude")
    assert cfgmod.resolve_power("low", "claude", profile).model == "haiku"
    assert cfgmod.get_config_value("base_dir") == "/p4"


def test_values_needing_escaping_survive(cfg_file):
    """Hand-rolled escaping is what made the old writer wrong; prove the new one isn't."""
    tricky = '/path/with "quotes" and \\backslash\\ and = signs'
    cfgmod.write_config_key("base_dir", tricky)
    assert cfgmod.get_config_value("base_dir") == tricky


# --- the default agent CLI ---------------------------------------------------


def test_default_cli_is_the_builtin_when_unset(cfg_file):
    cfg_file.write_text(_POWER)
    assert cfgmod.resolve_default_cli() == cfgmod.BUILTIN_DEFAULT_CLI == "claude"


def test_default_cli_is_read_from_the_config(cfg_file):
    cfg_file.write_text('config_version = 2\ndefault_cli = "opencode"\n')
    assert cfgmod.resolve_default_cli() == "opencode"


def test_default_cli_is_normalized(cfg_file):
    """The consumers lowercase what they read; do it once, here, so they agree."""
    cfg_file.write_text('config_version = 2\ndefault_cli = "  OpenCode  "\n')
    assert cfgmod.resolve_default_cli() == "opencode"


def test_a_malformed_default_cli_reads_as_unset(cfg_file):
    """Never an exception: this is read on the way into an unattended week-long run,
    and a config that has gone wrong must degrade to the built-in, not end the run.
    An unknown *name* is a different thing and is rejected by whoever owns the
    registry — core knows no backends."""
    for bad in (
        "default_cli = 3\n", 'default_cli = ""\n', 'default_cli = "   "\n',
        "default_cli = true\n", 'default_cli = ["opencode"]\n',
    ):
        cfg_file.write_text(f"config_version = 2\n{bad}")
        assert cfgmod.resolve_default_cli() == "claude", bad


def test_writing_the_default_cli_preserves_the_rest(cfg_file):
    cfg_file.write_text(_POWER)
    cfgmod.write_default_cli("OpenCode")
    data = tomllib.loads(cfg_file.read_text())
    assert data["default_cli"] == "opencode"
    assert data["profiles"]["claude"]["powers"]["high"] == {
        "model": "opus",
        "effort": "high",
    }


def test_default_cli_does_not_bump_the_schema(cfg_file):
    """Additive keys never bump CONFIG_VERSION: an older tool that ignores this one
    falls back to the same built-in it always used, which is not a wrong answer."""
    cfg_file.write_text('config_version = 2\ndefault_cli = "opencode"\n')
    assert cfgmod.config_version_of(tomllib.loads(cfg_file.read_text())) == 2
    assert cfgmod.check_config_version() == 2


# --- unification + migration -------------------------------------------------


def test_path_is_stablemate_not_workhorse(monkeypatch):
    monkeypatch.delenv(cfgmod.CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    assert cfgmod.config_path().parent.name == "stablemate"


def test_legacy_files_are_read_when_unified_is_absent(tmp_path, monkeypatch):
    """An existing per-tool setup keeps working with no manual migration step.

    Legacy v1 files are migrated to v2 in memory on read, so a round of
    ``resolve_power`` sees the new shape without a write.
    """
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
    # Migration runs in memory: power.high.claude (v1) is now inside
    # profiles.claude.powers.high (v2).
    profile = cfgmod.select_profile(cfgmod.load_config(), "claude")
    assert cfgmod.resolve_power("high", "claude", profile).model == "opus"


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
    assert data["profiles"]["claude"]["powers"]["high"]["model"] == "opus"
    assert data["config_version"] == 2


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
    """A broken config must not crash a week-long unattended run.

    A corrupt TOML file fails to parse, so `_read` returns `{}`. The migration then
    lifts that empty v1 into an empty v2 (a `config_version = 2` and `profiles = {}`
    shell), so the assertion accepts the migrated shape rather than `{}`.
    """
    cfg_file.write_text("this is not [ valid toml =")
    data = cfgmod.load_config()
    assert data.get("config_version") == cfgmod.CONFIG_VERSION
    assert data.get("profiles") == {}
    # A resolver call against the migrated empty config still returns empty.
    profile = cfgmod.select_profile(data, "claude") if False else {}
    assert cfgmod.resolve_power("high", "claude", profile) == cfgmod.PowerMapping()


# --- schema versioning -------------------------------------------------------
#
# One file, written by tools installed separately and versioned independently: two pipx
# venvs each hold their own stablemate-core, and the config path is per-user, not per
# venv. Nothing in packaging can make those agree, so the file carries the guard.


@pytest.fixture(autouse=True)
def _reset_warn_cache():
    """The read-warning is once-per-version-per-process; tests must not inherit it."""
    cfgmod._warned_too_new.clear()


def test_writes_stamp_the_schema_version(cfg_file):
    cfgmod.write_config_key("base_dir", "/p")
    data = tomllib.loads(cfg_file.read_text())
    assert data[cfgmod.CONFIG_VERSION_KEY] == cfgmod.CONFIG_VERSION


def test_unversioned_config_is_migrated_in_memory(cfg_file):
    """A v1 file (no `config_version` key, since the key was added with v1) is
    migrated to v2 in memory on read, so resolvers only need to know the current
    shape. The file on disk stays v1 until a write bumps it."""
    cfg_file.write_text(_POWER.replace("config_version = 2\n", ""))
    data = cfgmod.load_config()
    # Migration lifted power.* into profiles.*.powers.*.
    assert data["profiles"]["claude"]["powers"]["high"]["model"] == "opus"
    assert data["profiles"]["claude"]["cli"] == "claude"
    # The file on disk is still v1.
    assert cfgmod.config_version_of(tomllib.loads(cfg_file.read_text())) == 1


def test_config_version_of_rejects_a_bool(cfg_file):
    """bool is an int subclass; `config_version = true` must not read as v1."""
    assert cfgmod.config_version_of({cfgmod.CONFIG_VERSION_KEY: True}) == 1


def test_write_refuses_a_newer_config(cfg_file):
    """The load-bearing guard: an old tool must not serialize back a schema it cannot
    represent, dropping the keys it does not understand — the original bug, exactly.

    `config_version = 3` is rewritten manually rather than concatenated with `_POWER`
    (which itself declares `config_version = 2`): TOML forbids duplicate keys, and a
    duplicate-key parse failure would silently fall through to the empty-config path.
    """
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
    # And the file is untouched.
    data = tomllib.loads(cfg_file.read_text())
    assert "base_dir" not in data
    assert data["profiles"]["claude"]["powers"]["high"]["model"] == "opus"


def test_reads_of_a_newer_config_survive_but_warn(cfg_file, caplog):
    """Reads stay fail-soft: resolve_power re-reads per node, so raising here would kill
    a week-long run. It must not be SILENT, though — that is the failure being guarded."""
    cfg_file.write_text(
        'config_version = 3\n'
        '[profiles.claude]\n'
        'cli = "claude"\n'
        '[profiles.claude.powers.high]\n'
        'model = "opus"\n'
    )

    with caplog.at_level("WARNING"):
        profile = cfgmod.select_profile(cfgmod.load_config(), "claude")
        assert cfgmod.resolve_power("high", "claude", profile).model == "opus"

    assert "understands v" in caplog.text


def test_the_read_warning_is_not_repeated(cfg_file, caplog):
    """Per-node re-reads must not bury an unattended run in duplicate warnings."""
    cfg_file.write_text(f"{cfgmod.CONFIG_VERSION_KEY} = {cfgmod.CONFIG_VERSION + 1}\n")
    with caplog.at_level("WARNING"):
        for _ in range(5):
            cfgmod.load_config()
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
    """Exercises the walk that bumps CONFIG_VERSION through unknown territory — the
    mechanism is proven before the release that needs it rather than after."""
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


# --- v1 → v2 shape migration --------------------------------------------------


def test_v1_migrates_to_v2_in_memory_on_read(cfg_file):
    """The v1→v2 lift: top-level [power.*] / [default.*] become [profiles.<cli>.*],
    and [harness.*] becomes [cli.*]. The file on disk stays v1 until a write."""
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
    data = cfgmod.load_config()
    # top-level [power.*] / [default.*] / [harness.*] are gone.
    assert "power" not in data
    assert "default" not in data or not isinstance(data["default"], dict) or not data["default"]
    assert "harness" not in data
    # [power.high.opencode] became profiles.opencode.powers.high.
    assert data["profiles"]["opencode"]["cli"] == "opencode"
    assert data["profiles"]["opencode"]["powers"]["high"]["model"] == "gpt-5"
    # [default.claude] became profiles.claude.default.
    assert data["profiles"]["claude"]["default"]["model"] == "sonnet"
    # [harness.opencode] became [cli.opencode].
    assert data["cli"]["opencode"]["env"] == {"X": "1"}


def test_v1_profile_with_default_cli_is_renamed_to_cli(cfg_file):
    cfg_file.write_text(
        'config_version = 1\n'
        '\n[profiles.deepseek]\n'
        'default_cli = "opencode"\n'
        '\n[profiles.deepseek.default.opencode]\n'
        'model = "deep-v4"\n'
    )
    data = cfgmod.load_config()
    assert data["profiles"]["deepseek"]["cli"] == "opencode"
    assert "default_cli" not in data["profiles"]["deepseek"]
    assert data["profiles"]["deepseek"]["default"]["model"] == "deep-v4"


def test_v1_profile_without_a_cli_is_a_config_error():
    """A v1 profile with no `default_cli` cannot migrate to v2 — its `cli` field is
    required, and the migration refuses rather than silently dropping the profile (a
    silent drop is the kind of misconfigured-config data-loss the schema guard exists to
    prevent). ``load_config`` swallows the migration error on read (fail-soft on
    unparseable data), so the assertion is against the migration function directly."""
    import tomllib

    v1 = tomllib.loads(
        '[profiles.broken]\n[profiles.broken.power.high.opencode]\nmodel = "x"\n'
    )
    with pytest.raises(cfgmod.ConfigVersionError, match="cli field"):
        cfgmod._migrate_v1_to_v2(v1)


# --- [qa_tools.*] -------------------------------------------------------------


def test_load_config_reads_qa_tools_table(cfg_file):
    """`[qa_tools.<name>]` is read generically, like `[power.*]` — no dedicated accessor.

    ostler's tool registry (`ostler.qa.tools`) reads this table straight off
    `load_config()["qa_tools"]`; this is the contract that call depends on.
    """
    cfg_file.write_text(
        'config_version = 2\n'
        '[qa_tools.tesseract]\ncommand = "tesseract"\ndescription = "OCR"\n'
        '[qa_tools."ocr-diff"]\ncommand = "/opt/bin/ocr-diff"\n'
    )

    data = cfgmod.load_config()

    assert data["qa_tools"]["tesseract"] == {"command": "tesseract", "description": "OCR"}
    assert data["qa_tools"]["ocr-diff"] == {"command": "/opt/bin/ocr-diff"}


def test_writing_a_key_preserves_qa_tools_table(cfg_file):
    """The same non-destructive-write guarantee [power.*] gets, for [qa_tools.*]."""
    cfg_file.write_text('config_version = 2\n[qa_tools.tesseract]\ncommand = "tesseract"\n')

    cfgmod.write_config_key("base_dir", "/some/path")

    data = tomllib.loads(cfg_file.read_text())
    assert data["qa_tools"]["tesseract"] == {"command": "tesseract"}
    assert data["base_dir"] == "/some/path"


# --- worktree_dir -------------------------------------------------------------


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


# --- timeout_scale: the per-tier wall-clock multiplier -----------------------

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
    profile = cfgmod.select_profile(cfgmod.load_config(), "claude")

    assert cfgmod.resolve_power("high", "claude", profile).timeout_scale == 2.5


def test_timeout_scale_is_none_when_the_tier_omits_it(cfg_file):
    """Unset, not 1.0 — so the caller can still fall through to the profile's default."""
    cfg_file.write_text(_SCALED)
    profile = cfgmod.select_profile(cfgmod.load_config(), "claude")

    assert cfgmod.resolve_power("low", "claude", profile).timeout_scale is None


def test_timeout_scale_falls_through_to_the_profile_default(cfg_file):
    cfg_file.write_text(_SCALED)
    profile = cfgmod.select_profile(cfgmod.load_config(), "claude")

    assert cfgmod.resolve_backend_default("claude", profile).timeout_scale == 1.5


def test_timeout_scale_survives_a_write(cfg_file):
    cfg_file.write_text(_SCALED)

    cfgmod.write_config_key("base_dir", "/some/path")

    profile = cfgmod.select_profile(cfgmod.load_config(), "claude")
    assert cfgmod.resolve_power("high", "claude", profile).timeout_scale == 2.5


def test_an_integer_timeout_scale_reads_as_a_float(cfg_file):
    cfg_file.write_text(
        'config_version = 2\n'
        '[profiles.claude]\ncli = "claude"\n'
        '[profiles.claude.powers.high]\ntimeout_scale = 3\n'
    )
    profile = cfgmod.select_profile(cfgmod.load_config(), "claude")

    assert cfgmod.resolve_power("high", "claude", profile).timeout_scale == 3.0


@pytest.mark.parametrize("raw", ["\"2.5\"", "true", "0", "-1", "inf", "nan"])
def test_a_malformed_timeout_scale_reads_as_unset(cfg_file, raw):
    """Every rejected value would be worse than the absence it degrades to.

    `true` reads as 1.0 through the int subclass; 0 and a negative time every node
    out instantly; `inf` silently unbounds the whole run.
    """
    cfg_file.write_text(
        f'config_version = 2\n'
        f'[profiles.claude]\ncli = "claude"\n'
        f'[profiles.claude.powers.high]\ntimeout_scale = {raw}\n'
    )
    profile = cfgmod.select_profile(cfgmod.load_config(), "claude")

    assert cfgmod.resolve_power("high", "claude", profile).timeout_scale is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))