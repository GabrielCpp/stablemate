"""Home-config persistence, shared by every stablemate tool.

One file, ``~/.config/stablemate/config.toml`` (platform-appropriate), read and
written by workhorse and farrier alike. It used to be one file *per tool*, which meant
each tool's own ``config set-base`` wrote to a different place
and could silently disagree about ``library_dir`` / ``stablemate_dir`` / ``base_dir`` —
keys that only mean anything if every tool sees the same value.

Legacy per-tool files are still read when the unified one is absent, and the first
write migrates them, so an existing setup keeps working without a manual step.

**The file carries a schema version, and that is what actually prevents skew.** One
config is shared by tools that are installed separately and versioned independently —
``pipx install workhorse-agent`` and ``pipx install farrier`` are two venvs, each with
its own copy of this module, both writing this one file. No packaging arrangement can
make them agree: the config path comes from ``platformdirs``, so it is per *user*, not
per venv, and pip's resolver never sees the other venv. The guard therefore belongs on
the file, not on the code that reaches it — see :data:`CONFIG_VERSION`.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_dir

logger = logging.getLogger(__name__)

CONFIG_PATH_ENV = "STABLEMATE_CONFIG"
# The pre-unification override. Honored so an existing WORKHORSE_CONFIG export keeps
# pointing at the file its owner meant.
LEGACY_CONFIG_PATH_ENV = "WORKHORSE_CONFIG"

# Per-tool files predating the unified one. Read (merged, in order) when no unified
# config exists; the next write folds them into one. farrier's is listed here on
# purpose: these keys are shared, so workhorse inheriting a farrier-configured
# `library_dir` is the point, not a leak.
_LEGACY_APPS = ("workhorse", "farrier")

# The schema this build reads and writes.
#
# v1 (the unified config.toml) carried power/default/harness as top-level tables and
# profiles as a namespace of named, arbitrary-shape overrides. v2 moves the model
# selection tables under `[profiles.<cli>]` and renames `[harness.<cli>]` to
# `[cli.<cli>]`. Every profile carries a required `cli` field naming the CLI it runs
# under; a profile whose key matches its `cli` field is the auto-selected default for
# that CLI. Exactly one profile per `cli` value.
#
# DELIBERATELY NOT core's own version. Coupling the two would bump the schema on every
# patch release, and every bump locks out every tool that has not upgraded yet — turning
# a rare correctness guard into constant friction. Bump this ONLY for a change that an
# older reader would get *wrong*: a renamed or moved key, or one whose meaning changed.
# Purely additive keys never bump it, because an old reader ignoring a key it does not
# know is already safe.
#
# Git is the history: bump this in its own commit, alongside the migration that carries
# a config forward, and `git log -S 'CONFIG_VERSION = '` finds what changed and when.
CONFIG_VERSION = 2

CONFIG_VERSION_KEY = "config_version"

# The key naming the agent CLI a run drives when the invocation names none, and the
# name used when it is unset. Additive, so it does not bump CONFIG_VERSION: an older
# reader that ignores the key falls back to the same built-in it always used.
DEFAULT_CLI_KEY = "default_cli"
BUILTIN_DEFAULT_CLI = "claude"

# The namespace of named model sets: `[profiles.<name>]`. Each profile carries its
# own `cli` field naming the CLI it runs under, plus `powers.<tier>` and a `default`
# table for model resolution. Plural where its siblings are singular, because it is a
# namespace of named things rather than one table.
PROFILES_KEY = "profiles"

# The key naming the CLI a profile runs under. Required on every profile.
PROFILE_CLI_KEY = "cli"

# The key under a profile that holds per-tier model mappings (plural — the table
# contains one entry per tier).
PROFILE_POWERS_KEY = "powers"

# The key under a profile that holds the profile's fallback model/effort (singular —
# one entry, not a per-CLI map; the profile's `cli` field already names its CLI).
PROFILE_DEFAULT_KEY = "default"

# The top-level key under which per-CLI global config (env vars) lives. Renamed from
# `harness` in v2 to make room for `[profiles.<cli>]`; the resolution order is
# unchanged — unnarrowed, applies to every profile that runs the named CLI.
CLI_KEY = "cli"

# The key inside a `[cli.<name>]` table that holds the env-var mapping.
CLI_ENV_KEY = "env"

# The per-tier fallback key inside a legacy `[power.<tier>]` table: the entry used when
# the tier names no table for the active backend. Not a backend name. Carried forward
# for v1-shaped reads during the transition; v2 has no per-backend nesting.
BACKEND_FALLBACK_KEY = "default"

# Steps that carry a config forward one schema version: _MIGRATIONS[n] takes a v(n)
# config and returns a v(n+1) one. v1→v2 lifts top-level [power.*]/[default.*] into
# [profiles.*], renames [harness.*] to [cli.*], and renames the per-profile
# `default_cli` field to `cli`. Populated below, after the migration functions are
# defined — the dict cannot reference a name Python has not yet bound.
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class ConfigVersionError(RuntimeError):
    """A config this build must not touch — it was written by a newer stablemate-core.

    Raised on WRITE, never on read. Writing is where the damage happens: a writer
    serializes the whole file back, so one that does not understand a key drops or
    mangles it. That is not hypothetical here — it is the bug this module was created
    to fix, where a hand-rolled writer stringified a table it did not understand and
    every node silently fell back to the default model, with no error anywhere.
    """


class ConfigError(ValueError):
    """The config is shaped wrong for the schema it declares.

    Distinct from :class:`ConfigVersionError` (which is about *version mismatch*): a
    ConfigError is a structural problem in a v2-shaped file — a missing `cli` field on
    a profile, two profiles claiming the same `cli`. The schema version is current; the
    data is just wrong.

    A profile that names a misspelled CLI does NOT raise here. Core knows no backend
    registry, and a misspelling is the harness boundary's job to catch — same place
    that rejects an unknown `--cli` today.
    """


def _core_version() -> str:
    try:
        return metadata.version("stablemate-core")
    except metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return "unknown"


def _default_config_path() -> Path:
    """~/Library/Application Support/stablemate on macOS, %APPDATA%\\stablemate on
    Windows, ~/.config/stablemate on Linux."""
    return Path(user_config_dir("stablemate")) / "config.toml"


def legacy_config_paths() -> list[Path]:
    return [Path(user_config_dir(app)) / "config.toml" for app in _LEGACY_APPS]


@dataclass(frozen=True)
class PowerMapping:
    model: str | None = None
    effort: str | None = None
    #: Multiplier on every per-node wall-clock budget resolved for this tier. The node
    #: numbers state the *shape* of the work ("a QA plan is about twenty minutes"); this
    #: states how fast this model executes a unit of it. ``None`` means "unset", so the
    #: same "first non-None wins" fallthrough to ``[default.<backend>]`` applies as to
    #: model and effort — a literal ``1.0`` here would stop that fallthrough.
    timeout_scale: float | None = None


def config_path() -> Path:
    raw = os.environ.get(CONFIG_PATH_ENV) or os.environ.get(LEGACY_CONFIG_PATH_ENV)
    if raw:
        return Path(raw).expanduser()
    return _default_config_path()


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        # A corrupt or unreadable config must not take down an unattended run; an
        # empty config degrades to "nothing configured", which every caller handles.
        return {}


def _path_is_explicit() -> bool:
    return bool(
        os.environ.get(CONFIG_PATH_ENV) or os.environ.get(LEGACY_CONFIG_PATH_ENV)
    )


def config_version_of(cfg: dict[str, Any]) -> int:
    """The schema version a loaded config declares. Unversioned means v1.

    Every config predating this key is v1-shaped by definition: v1 IS the unified file,
    and the legacy per-tool files merge into a v1 config. So a missing key is not
    "unknown", it is 1 — which is why this never guesses or fails.
    """
    raw = cfg.get(CONFIG_VERSION_KEY)
    # bool is an int subclass, and `config_version = true` must not read as v1.
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return 1
    return raw


def _too_new_message(found: int) -> str:
    # No attempt to name the release that introduced v<found>: this build predates it by
    # definition — that is why it is refusing — so it cannot know. The two versions it
    # CAN state are the two that matter to whoever has to fix this.
    return (
        f"{config_path()} uses config schema v{found}, written by a newer "
        f"stablemate-core; this is stablemate-core {_core_version()}, which supports up to "
        f"v{CONFIG_VERSION}. Refusing to write it — doing so would drop the keys this "
        f"build does not understand. Upgrade this tool (its stablemate-core), or set "
        f"${CONFIG_PATH_ENV} to a different file."
    )


# Reads are warned about once per version, not per call: resolve_power re-reads the
# config for every node, so warning per call would bury a week-long run in duplicates.
_warned_too_new: set[int] = set()


def _warn_if_too_new(cfg: dict[str, Any]) -> None:
    found = config_version_of(cfg)
    if found <= CONFIG_VERSION or found in _warned_too_new:
        return
    _warned_too_new.add(found)
    logger.warning(
        "%s uses config schema v%d; this build understands v%d. Reading it anyway, but "
        "keys it does not share may be missing or misread — upgrade this tool.",
        config_path(),
        found,
        CONFIG_VERSION,
    )


def check_config_version(cfg: dict[str, Any] | None = None) -> int:
    """Raise :class:`ConfigVersionError` if the config is newer than this build.

    For CLIs to call at STARTUP, where failing is safe and actionable. Deliberately not
    called from :func:`load_config`: ``resolve_power`` re-reads the config per node, so
    raising there would kill a running workflow — and workhorse's design target is a run
    that survives a week unattended. A run that has already started keeps going on a
    best-effort read; the guard that actually protects the file is on writes.
    """
    data = cfg if cfg is not None else load_config()
    found = config_version_of(data)
    if found > CONFIG_VERSION:
        raise ConfigVersionError(_too_new_message(found))
    return found


def load_config() -> dict[str, Any]:
    """The effective config: the unified file, else the merged legacy per-tool files.

    The legacy fallback applies ONLY to the default path. An explicitly named config
    ($STABLEMATE_CONFIG) that happens not to exist means "this file", not "and also
    whatever is in ~/.config/workhorse" — silently reading another file would ignore
    what the caller asked for, and makes the env var useless for isolating a run.

    Older schemas are migrated in-memory on read so resolvers only need to know the
    current shape; the file on disk stays at its declared version until a write lifts
    it. A migration that cannot run (no step registered) is the same :class:
    `ConfigVersionError` a write would raise — but reads stay fail-soft and skip the
    lift rather than kill a week-long run, which is why this path does not call
    `_migrate_forward` and its backup side-effect.
    """
    path = config_path()
    if path.is_file():
        data = _read(path)
        found = config_version_of(data)
        if found < CONFIG_VERSION:
            try:
                data = _walk_migrations(data, found)
            except ConfigVersionError:
                # Fall through: the read-warning below is the operator's signal,
                # and a load that fails to migrate should not end the run.
                pass
        _warn_if_too_new(data)
        return data
    if _path_is_explicit():
        return {}

    merged: dict[str, Any] = {}
    for legacy in legacy_config_paths():
        merged.update(_read(legacy))
    found = config_version_of(merged)
    if found < CONFIG_VERSION:
        try:
            merged = _walk_migrations(merged, found)
        except ConfigVersionError:
            pass
    _warn_if_too_new(merged)
    return merged


def write_config_key(key: str, value: str) -> None:
    """Persist a single top-level string key, preserving every other key.

    Serialized with a real TOML writer. It used to be ``f'{k} = "{v}"'`` over
    ``cfg.items()``, which stringified nested tables: a single ``config set-base`` turned
    the whole ``[power.*]`` table into a Python-repr string, after which ``resolve_power``
    saw a str instead of a dict and silently returned an empty mapping — every node
    quietly falling back to the default model, with no error anywhere.

    When only legacy files exist, this writes the merged result to the unified path,
    which is what migrates them.

    Refuses (:class:`ConfigVersionError`) when the file on disk is newer than
    :data:`CONFIG_VERSION`. The check is on the **raw disk version**, not on the
    in-memory version: ``load_config`` migrates older schemas forward so callers always
    see the current shape, and a check against the migrated shape would never fire.
    This is the one guard that holds no matter how the tools were installed — two pipx
    venvs, two vendored copies, one shared venv — because it defends the file rather
    than trusting the code that reaches it. An older config is carried forward first,
    so a write never mixes schemas.
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _read(path)
    cfg = load_config()

    found = config_version_of(raw)
    if found > CONFIG_VERSION:
        raise ConfigVersionError(_too_new_message(found))
    if found < CONFIG_VERSION:
        cfg = _migrate_forward(cfg, found, path)

    cfg[key] = value
    # Stamped on every write, which is what closes the door behind a migration: once a
    # newer build has written, an older one refuses rather than clobbering.
    cfg[CONFIG_VERSION_KEY] = CONFIG_VERSION
    with path.open("wb") as handle:
        tomli_w.dump(cfg, handle)


def _migrate_forward(cfg: dict[str, Any], from_version: int, path: Path) -> dict[str, Any]:
    """Carry a config from ``from_version`` up to :data:`CONFIG_VERSION`, one step at a time.

    Backs the file up first. Migration is a one-way door — the stamped result locks out
    every not-yet-upgraded tool on the machine — so the previous file has to survive for
    a downgrade to be possible at all.
    """
    if path.is_file():
        backup = path.with_name(f"{path.name}.v{from_version}.bak")
        try:
            shutil.copy2(path, backup)
        except OSError as exc:
            raise ConfigVersionError(
                f"cannot back up {path} to {backup} before migrating it to schema "
                f"v{CONFIG_VERSION}: {exc}"
            ) from exc
        logger.warning(
            "migrating %s from config schema v%d to v%d; the previous file is saved at "
            "%s. Tools still on an older stablemate-core will refuse to write it.",
            path,
            from_version,
            CONFIG_VERSION,
            backup,
        )

    return _walk_migrations(cfg, from_version)


def _walk_migrations(cfg: dict[str, Any], from_version: int) -> dict[str, Any]:
    """Apply the migrations from ``from_version`` up to :data:`CONFIG_VERSION`, no I/O.

    The in-memory sibling of :func:`_migrate_forward` — same walk, no file backup. Used
    by :func:`load_config` so resolvers always see the current schema shape even when
    the file on disk is older; a write still has to go through :func:`_migrate_forward`
    to bump the disk-side version.
    """
    data = dict(cfg)
    for version in range(from_version, CONFIG_VERSION):
        step = _MIGRATIONS.get(version)
        if step is None:
            raise ConfigVersionError(
                f"no migration registered from config schema v{version} to "
                f"v{version + 1}; cannot carry forward safely."
            )
        data = step(data)
    return data


def _migrate_v1_to_v2(cfg: dict[str, Any]) -> dict[str, Any]:
    """Carry a v1 config to v2.

    Three lifts:

    - Top-level ``[power.<tier>.<backend>]`` → ``[profiles.<backend>.powers.<tier>]``,
      creating the CLI-named profile (with ``cli = "<backend>"``) if absent.
    - Top-level ``[default.<backend>]`` → ``[profiles.<backend>.default]``.
    - Top-level ``[harness.<backend>]`` → ``[cli.<backend>]`` (rename only).

    Profiles already present get their ``default_cli`` field renamed to ``cli`` and
    their ``[power.*]`` / ``[default.*]`` keys lifted under the new nesting.

    Two profiles that would end up declaring the same ``cli`` value are a v1-v2
    contradiction and fail the migration; the operator picks one to keep.
    """
    data = dict(cfg)
    profiles = data.setdefault(PROFILES_KEY, {})
    if not isinstance(profiles, dict):
        profiles = {}
        data[PROFILES_KEY] = profiles

    # Lift [power.<tier>.<backend>] → [profiles.<backend>.powers.<tier>].
    power = data.pop("power", None)
    if isinstance(power, dict):
        for tier, by_backend in power.items():
            if not isinstance(by_backend, dict):
                continue
            for backend, mapping in by_backend.items():
                if not isinstance(mapping, dict):
                    continue
                profile = _ensure_cli_profile(profiles, str(backend))
                powers = profile.setdefault(PROFILE_POWERS_KEY, {})
                if not isinstance(powers, dict):
                    powers = {}
                    profile[PROFILE_POWERS_KEY] = powers
                # Only the FIRST entry a tier sees becomes the auto-default's; later
                # ones (rare; v1 had no per-profile merge) keep their slot.
                powers.setdefault(tier, mapping)

    # Lift [default.<backend>] → [profiles.<backend>.default].
    default_table = data.pop("default", None)
    if isinstance(default_table, dict):
        for backend, mapping in default_table.items():
            # v1's [default.<backend>] was a single key holding the model string
            # (e.g. `default.claude = "sonnet"`); v2's [profiles.<cli>.default] is
            # a table that may carry model, effort and timeout_scale. Both shapes are
            # accepted; a string becomes the model of a one-key table.
            if isinstance(mapping, dict):
                entry = mapping
            elif isinstance(mapping, str) and mapping.strip():
                entry = {"model": mapping.strip()}
            else:
                continue
            profile = _ensure_cli_profile(profiles, str(backend))
            profile.setdefault(PROFILE_DEFAULT_KEY, entry)

    # Rename [harness.<backend>] → [cli.<backend>].
    harness = data.pop("harness", None)
    if isinstance(harness, dict):
        data[CLI_KEY] = harness

    # For each profile: rename default_cli → cli, lift its own [power.*] and [default.*]
    # into the new shape.
    for name, profile in list(profiles.items()):
        if not isinstance(profile, dict):
            continue
        if PROFILE_CLI_KEY not in profile:
            legacy = profile.pop("default_cli", None)
            if isinstance(legacy, str) and legacy.strip():
                profile[PROFILE_CLI_KEY] = legacy.strip().lower()
            else:
                raise ConfigVersionError(
                    f"[profiles.{name}] has no cli field and no legacy default_cli — "
                    f"cannot migrate to schema v{CONFIG_VERSION}. Add "
                    f'cli = "<one of the configured CLIs>" to {name!r}.'
                )
        else:
            profile.pop("default_cli", None)

        nested_power = profile.pop("power", None)
        if isinstance(nested_power, dict):
            powers = profile.setdefault(PROFILE_POWERS_KEY, {})
            if not isinstance(powers, dict):
                powers = {}
                profile[PROFILE_POWERS_KEY] = powers
            for tier, by_backend in nested_power.items():
                if not isinstance(by_backend, dict):
                    continue
                for backend, mapping in by_backend.items():
                    if not isinstance(mapping, dict):
                        continue
                    powers.setdefault(tier, mapping)

        nested_default = profile.pop("default", None)
        if isinstance(nested_default, dict):
            cli = profile_cli(profile)
            # A v1 profile's `default` is either flat (just written under v2 rules:
            # model/effort/timeout_scale at the top level) or per-backend (legacy
            # `[profiles.X.default.<backend>]` with backend-named subtables). Flat goes
            # through unchanged; per-backend picks the entry whose name matches the
            # profile's `cli` and drops the rest.
            if cli and any(
                key not in {"model", "effort", "timeout_scale"} for key in nested_default
            ):
                entry = nested_default.get(cli)
                if isinstance(entry, dict):
                    profile.setdefault(PROFILE_DEFAULT_KEY, entry)
            else:
                profile.setdefault(PROFILE_DEFAULT_KEY, nested_default)

    _reject_duplicate_cli(profiles)

    data[CONFIG_VERSION_KEY] = CONFIG_VERSION
    return data


def _ensure_cli_profile(profiles: dict[str, Any], cli: str) -> dict[str, Any]:
    """Get-or-create the profile that names ``cli`` as its CLI.

    Auto-created profiles get ``cli = "<name>"`` so the auto-select rule finds them.
    """
    profile = profiles.get(cli)
    if not isinstance(profile, dict):
        profile = {PROFILE_CLI_KEY: cli}
        profiles[cli] = profile
    profile.setdefault(PROFILE_CLI_KEY, cli)
    return profile


def _reject_duplicate_cli(profiles: dict[str, Any]) -> None:
    """Reject only the auto-default conflict — two profiles claiming to be the
    auto-default for the same CLI.

    Multiple profiles declaring the same ``cli`` is fine: the auto-select rule picks
    the one whose *key* matches the CLI (``[profiles.opencode]`` is the auto-default
    for opencode), and the others are explicit overrides selected via ``--profile``.

    What IS an error is two profiles whose keys both match the same CLI — which is
    impossible under TOML dict semantics (a dict has only one entry per key), so this
    function is a structural guard that mostly asserts invariants the file format
    already enforces. It is left here so a future shape (a list of profiles per CLI,
    say) cannot quietly relax the rule without a corresponding migration update.
    """
    seen: dict[str, str] = {}
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        cli = profile.get(PROFILE_CLI_KEY)
        if not isinstance(cli, str) or not cli.strip():
            continue
        normalized = cli.strip().lower()
        if normalized == name and normalized in seen:
            raise ConfigVersionError(
                f"[profiles.{name}] and [profiles.{seen[normalized]}] both claim to be "
                f"the auto-default for cli = {normalized!r}; a config may have at most "
                f"one CLI-named profile per CLI."
            )
        if normalized == name:
            seen[normalized] = name


# Populated now that the v1→v2 step is defined above; see the comment on _MIGRATIONS.
_MIGRATIONS[1] = _migrate_v1_to_v2


class UnknownProfileError(LookupError):
    """``--profile <name>`` named a profile the config does not define.

    A hard failure on purpose, and only ever raised where failing is safe: selecting a
    profile is a startup decision, and the alternative — falling back to the top-level
    tables — spends a week of unattended run on the wrong set of models with nothing in
    the log to say so.
    """


def _profiles_table(cfg: dict[str, Any]) -> dict[str, Any]:
    table = cfg.get(PROFILES_KEY)
    return table if isinstance(table, dict) else {}


def profile_names(cfg: dict[str, Any] | None = None) -> list[str]:
    """The names `[profiles.<name>]` defines, sorted. Empty when there are none."""
    data = cfg if cfg is not None else load_config()
    return sorted(name for name in _profiles_table(data) if isinstance(name, str))


def profile_cli(profile: dict[str, Any]) -> str | None:
    """The ``cli`` field a profile declares, lowercased and stripped.

    ``None`` for a profile that has no ``cli`` field or whose value is not a non-empty
    string — those are the malformed profiles every accessor below filters out, so a
    caller that only wants "the CLI this profile says it runs under" gets the same
    answer as the rest of the module.
    """
    raw = profile.get(PROFILE_CLI_KEY)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().lower()


def select_profile(cfg: dict[str, Any] | None, name: str) -> dict[str, Any]:
    """Narrow ``cfg`` to the named profile: the config every model resolver then reads.

    A profile **replaces** the top-level tables rather than layering over them, and this
    function is what makes that structurally true: it hands back the profile's own table,
    so :func:`resolve_power` and :func:`resolve_backend_default` need no notion of
    profiles at all — their ``cfg`` parameter was already the seam. ``[cli.*]`` stays
    outside for free, because it is resolved from the *unnarrowed* config.

    Every profile carries a required ``cli`` field naming the CLI it runs under;
    ``select_profile`` validates that the named profile has one. The CLI value itself
    is not checked against the backend registry — core knows no such registry, and a
    misspelling is the harness boundary's job to catch.

    Inheriting the top level was rejected because power tiers are opaque strings: no
    schema says which tiers exist, so "the profile did not mention ``max``, therefore it
    means the machine's ``max``" is a guess the config cannot state and the operator
    cannot see.

    An empty ``name`` means "no profile" and returns ``{}``, so a caller threading an
    unset selector gets the same answer it would have if the file defined no profiles
    at all: every resolver reads an empty mapping and the run runs without model flags.
    """
    data = cfg if cfg is not None else load_config()
    if not name:
        return {}
    profile = _profiles_table(data).get(name)
    if not isinstance(profile, dict):
        known = profile_names(data)
        listed = ", ".join(known) if known else "none defined"
        raise UnknownProfileError(
            f"unknown profile {name!r} in {config_path()} (known: {listed})"
        )
    if profile_cli(profile) is None:
        raise ConfigError(
            f"[profiles.{name}] has no cli field — every profile must declare the CLI "
            f"it runs under. Add `cli = \"<name>\"` to {name!r}."
        )
    return profile


def auto_select_profile(cfg: dict[str, Any] | None, active_cli: str) -> dict[str, Any] | None:
    """Find the profile whose ``cli`` field matches ``active_cli``.

    The auto-select rule: when the CLI a run resolves to (from `--cli`, `$AGENT_CLI`,
    or the top-level `default_cli`) matches a profile's `cli` field, that profile is
    the model set the run resolves from — no `--profile` needed.

    Returns the profile table, or ``None`` when nothing matches. The caller decides
    whether "no match" is an error (a `--profile`-less run that named a CLI with no
    matching profile) or a valid bare-CLI run (a run where the CLI's own default model
    is fine). v2 makes the latter the default: bare-CLI mode emits no model flags.
    """
    if not active_cli:
        return None
    cli = active_cli.strip().lower()
    for name, profile in _profiles_table(cfg if cfg is not None else load_config()).items():
        if not isinstance(profile, dict):
            continue
        if profile_cli(profile) == cli:
            return profile
    return None


def select_active_profile(
    cfg: dict[str, Any] | None,
    *,
    name: str = "",
    active_cli: str = "",
) -> dict[str, Any]:
    """The profile a run resolves models from: explicit name, else auto-pick by CLI, else none.

    Three branches, in order:

    1. ``name`` is set → :func:`select_profile` by name (raises :class:`UnknownProfileError`
       or :class:`ConfigError` if missing or malformed).
    2. ``active_cli`` is set → :func:`auto_select_profile` finds the matching profile,
       or returns ``{}`` (bare-CLI mode) if nothing matches.
    3. Neither → bare-CLI mode, ``{}``.

    Bare-CLI mode is a valid state: no profile narrows the resolver's view, and every
    resolver returns an empty mapping. The workflow then invokes the CLI without
    ``--model`` or ``--effort`` flags, and the CLI uses its own built-in default.

    ``[cli.*]`` (harness env) is always resolved from the unnarrowed config — see
    :func:`resolve_harness_env` — so a profile that does not name a CLI-specific env
    table still inherits whatever the operator configured globally for that CLI.
    """
    if name:
        return select_profile(cfg, name)
    if active_cli:
        match = auto_select_profile(cfg, active_cli)
        if match is not None:
            return match
    return {}


def profile_backends(profile: dict[str, Any]) -> list[str]:
    """The CLI name a profile declares, lowercased, or empty.

    A profile is for one CLI, so the "backends it knows about" is the CLI it carries in
    its ``cli`` field — singular. The list-shaped return preserves the v1 contract
    workhorse's `_check_profile_resolves` iterates over, so a misspelled CLI on a
    profile is reported through the same boundary that always reported it.

    **Nothing here is validated**: core knows no backend registry, so a misspelling is
    rejected where every other bad backend name already is, at the boundary that
    resolves the adapter. This function only says which name was declared.
    """
    cli = profile_cli(profile)
    return [cli] if cli else []


def profile_has_backend(profile: dict[str, Any], backend: str) -> bool:
    """Whether a profile is for ``backend``.

    True when the profile's ``cli`` field equals ``backend``. The presence of model
    tables is irrelevant: a profile that declares only ``cli`` is meaningful — it
    selects the CLI (and its harness env) for the run, and the workflow runs in
    bare-CLI mode without model overrides.

    This is the post-v2 form of the v1 "no entries for the backend" check; the
    backend-keyed structure that made v1's answer nontrivial is gone, and the answer
    is a single equality test.
    """
    return profile_cli(profile) == backend


def _positive_finite(raw: Any) -> float | None:
    """A strictly positive, finite float, or ``None`` for anything else.

    Everything rejected here would be worse than the absence it degrades to: ``true``
    reads as ``1.0`` because bool is an int subclass, ``0`` and a negative make every
    node time out instantly, and ``inf`` silently unbounds every node in the run — a
    typo must not buy an unattended run an infinite budget.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _mapping_from_table(table: dict[str, Any]) -> PowerMapping:
    model = table.get("model")
    effort = table.get("effort")
    return PowerMapping(
        model=model if isinstance(model, str) and model else None,
        effort=effort if isinstance(effort, str) and effort else None,
        timeout_scale=_positive_finite(table.get("timeout_scale")),
    )


def resolve_power(power: str | None, backend: str, cfg: dict[str, Any] | None = None) -> PowerMapping:
    """The model/effort/timeout_scale for ``power`` on the ``backend`` the ``cfg`` runs.

    ``cfg`` here is the *narrowed profile* — the table :func:`select_active_profile`
    returned, which is for one CLI. The answer is ``profile.powers.<power>``: a flat
    mapping (model/effort/timeout_scale) with no per-backend nesting, because the
    profile itself is the per-CLI narrowing.

    ``backend`` is the CLI the caller intends to run under; when ``cfg`` declares a
    different ``cli`` field, the resolver returns empty — the cross-CLI misuse that
    v1 could only spot at the harness boundary now surfaces here, where a run that
    asked the wrong profile would otherwise quietly bill on the wrong CLI's models.

    An empty mapping is what bare-CLI mode returns: no profile narrowed the resolver's
    view, and the CLI uses its own default model with no ``--model`` or ``--effort``
    flag emitted by the workflow.
    """
    if not power:
        return PowerMapping()
    data = cfg if cfg is not None else load_config()
    if profile_cli(data) is not None and profile_cli(data) != backend:
        return PowerMapping()
    powers = data.get(PROFILE_POWERS_KEY)
    if not isinstance(powers, dict):
        return PowerMapping()
    tier_table = powers.get(power)
    if not isinstance(tier_table, dict):
        return PowerMapping()
    return _mapping_from_table(tier_table)


def resolve_backend_default(backend: str, cfg: dict[str, Any] | None = None) -> PowerMapping:
    """The profile's fallback model/effort from ``profile.default``.

    The per-CLI counterpart of a backend's hardcoded ``default_model``: it fills
    whatever a node's power tier (or the absence of one) left unset, so power-less
    nodes stop silently falling through to the harness's own default model. The
    ``backend`` argument is checked against ``cfg.cli`` for the same reason as
    :func:`resolve_power`: a profile that declares a different CLI is the cross-CLI
    misuse that v1 could only spot at the harness boundary.

    Missing or empty sections yield an empty mapping, never an error.
    """
    data = cfg if cfg is not None else load_config()
    if profile_cli(data) is not None and profile_cli(data) != backend:
        return PowerMapping()
    default_table = data.get(PROFILE_DEFAULT_KEY)
    if not isinstance(default_table, dict):
        return PowerMapping()
    return _mapping_from_table(default_table)


def resolve_harness_env(backend: str, cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """Extra environment variables to hand the ``<backend>`` CLI, from ``[cli.<backend>]``.

    ::

        [cli.opencode]
        env = { OPENCODE_DISABLE_AUTOCOMPACT = "1" }

    Every agent harness carries knobs that exist only as environment variables and
    have no CLI flag, and the right value for one harness is meaningless to another.
    This is the generic seam for them: workhorse learns no harness's vocabulary — it
    forwards whatever the operator names.

    Scoped per *CLI*, not per power tier, for two reasons. A knob like the one above is
    a property of the CLI, not of how hard a node is thinking, so a tier would be the
    wrong axis to repeat it along. And ``[cli.*]`` is resolved from the unnarrowed
    config (see :func:`select_active_profile`), so it applies to every profile that
    runs this CLI — a profile that silently un-exported a harness knob because it did
    not restate it would be a debugging trap.

    Non-string values are dropped rather than coerced: ``env = { FOO = 1 }`` is a TOML
    integer, and silently exporting ``"1"`` would make the config lie about what the
    process received. Any missing or mistyped section yields ``{}`` — a config read
    must never be what ends an unattended run.
    """
    data = cfg if cfg is not None else load_config()
    cli_table = data.get(CLI_KEY)
    if not isinstance(cli_table, dict):
        return {}
    backend_table = cli_table.get(backend)
    if not isinstance(backend_table, dict):
        return {}
    env_table = backend_table.get(CLI_ENV_KEY)
    if not isinstance(env_table, dict):
        return {}
    return {
        key: value
        for key, value in env_table.items()
        if isinstance(key, str) and key and isinstance(value, str)
    }


def resolve_default_cli(cfg: dict[str, Any] | None = None) -> str:
    """The agent CLI to drive when nothing on the invocation names one.

    Reads the top-level ``default_cli`` key::

        default_cli = "opencode"

    The precedence a tool applies around this is ``--cli`` → ``AGENT_CLI`` → here →
    :data:`BUILTIN_DEFAULT_CLI`. It lives in the config rather than as an argparse
    default because a default in the flag is only reachable by editing the tool: an
    operator whose machine is set up for one CLI otherwise has to name it on every
    run of every workflow, and the one they forget is the one that silently comes
    back on the built-in.

    **Nothing is validated here.** core knows no backend registry — the names are
    workhorse's — so a misspelling is rejected where every other bad CLI name already
    is, at the boundary that resolves the adapter, with the list of real names in the
    message. Only shape is normalized: a non-string, empty or whitespace value means
    "unset" rather than an error, because a config read must never be what ends an
    unattended run.
    """
    value = get_config_value(DEFAULT_CLI_KEY, cfg)
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return BUILTIN_DEFAULT_CLI


def write_default_cli(name: str) -> None:
    """Persist ``default_cli`` (the agent CLI a run drives when nothing names one)."""
    write_config_key(DEFAULT_CLI_KEY, name.strip().lower())


def get_config_value(name: str, cfg: dict[str, Any] | None = None) -> Any:
    data = cfg if cfg is not None else load_config()
    value: Any = data
    for part in name.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


# farrier spells this `read_config`; workhorse spells it `load_config`. Same file, same
# result — aliased rather than renamed so neither tool's call sites churn.
read_config = load_config


def write_library_dir(path: Path) -> None:
    """Persist ``library_dir`` (the overlay library root)."""
    write_config_key("library_dir", str(path))


def write_stablemate_dir(path: Path) -> None:
    """Persist ``stablemate_dir`` (a stablemate checkout)."""
    write_config_key("stablemate_dir", str(path))


def write_base_dir(path: Path) -> None:
    """Persist ``base_dir`` (the base library content path)."""
    write_config_key("base_dir", str(path))


def write_worktree_dir(path: Path) -> None:
    """Persist ``worktree_dir`` (the parent directory new git worktrees are cut into)."""
    write_config_key("worktree_dir", str(path))


def resolve_stablemate_dir() -> Path | None:
    """The configured stablemate checkout path, or None if unset."""
    configured = get_config_value("stablemate_dir")
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser().resolve()
    return None


def resolve_worktree_dir() -> Path | None:
    """The directory new git worktrees are cut into, or None if unset.

    Machine-local by nature: where a checkout's siblings may live is a property of the
    disk layout, not of the repo — one machine keeps them on a big data volume
    (``/mnt/data/worktrees``), another under ``~``. Persisting it here is what lets an
    agent cut a worktree without being told the path on every invocation, and what keeps
    that path out of any repo's committed instructions.

    Returns ``None`` when unset rather than guessing a default: the caller knows what a
    sensible sibling directory is for the repo in hand, and inventing one here would
    scatter worktrees across a machine that has a configured home for them.
    """
    configured = get_config_value("worktree_dir")
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser().resolve()
    return None


# ---------------------------------------------------------------------------
# groom's attendant: the one setting a dashboard toggle owns
# ---------------------------------------------------------------------------

#: The table groom's attendant settings live in: ``[groom.attend]``. Additive, so it does
#: not bump CONFIG_VERSION — an older reader has no attendant to configure, and
#: :func:`write_config_section` serializes with a real TOML writer, so a build that has
#: never heard of this table still preserves it on its own writes.
ATTEND_SECTION = "groom.attend"

ATTEND_OFF, ATTEND_SESSION, ATTEND_HEADLESS = "off", "session", "headless"
_ATTEND_MODES = (ATTEND_OFF, ATTEND_SESSION, ATTEND_HEADLESS)

#: The environment spelling that predates the config table. It stays readable as a
#: *fallback*, so an existing ``GROOM_ATTEND=session groom serve`` keeps working; the
#: config wins the moment the key is present, which is what makes the toggle authoritative.
ATTEND_MODE_ENV = "GROOM_ATTEND"
ATTEND_CLI_ENV = "GROOM_ATTEND_CLI"
ATTEND_DENY_ENV = "GROOM_ATTEND_DENY"

BUILTIN_ATTEND_CLI = "claude"

#: Where a resolved value came from, per field. The dashboard renders this: a toggle that
#: silently shadows an environment variable is a control the operator cannot trust.
CONFIG_SOURCE, ENV_SOURCE, DEFAULT_SOURCE = "config", "environment", "default"


@dataclass(frozen=True)
class AttendSettings:
    """The effective ``[groom.attend]`` settings, and where each one was read from."""

    mode: str = ATTEND_OFF
    #: The non-``off`` mode the toggle restores when it is switched back on. Without it a
    #: `session`-mode operator who toggles off and on again silently gets `headless`.
    last_mode: str = ATTEND_HEADLESS
    cli: str = BUILTIN_ATTEND_CLI
    deny: tuple[str, ...] = ()
    #: field name -> :data:`CONFIG_SOURCE` / :data:`ENV_SOURCE` / :data:`DEFAULT_SOURCE`.
    sources: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "last_mode": self.last_mode,
            "cli": self.cli,
            "deny": list(self.deny),
            "sources": dict(self.sources),
        }


def write_config_section(name: str, values: dict[str, Any]) -> None:
    """Persist one dotted table (``groom.attend``), preserving every other key.

    The nested-table sibling of :func:`write_config_key`, and it holds the same
    discipline for the same reasons: a real TOML writer over the loaded config, so a
    ``[power.*]`` or ``[profiles.*]`` table this build does not understand survives
    untouched; an older config carried forward first; a newer one refused outright.

    The disk-version check uses the **raw** file (see :func:`write_config_key`), not
    the in-memory migrated shape, so a v(n+1) file written by a newer build is refused
    even though ``load_config`` would have walked it forward for callers.

    The table is *replaced*, not merged. A settings pane sends the whole table it is
    showing, and a merge would make a removed deny entry unremovable.
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _read(path)
    cfg = load_config()

    found = config_version_of(raw)
    if found > CONFIG_VERSION:
        raise ConfigVersionError(_too_new_message(found))
    if found < CONFIG_VERSION:
        cfg = _migrate_forward(cfg, found, path)

    parts = name.split(".")
    table = cfg
    for part in parts[:-1]:
        nested = table.get(part)
        if not isinstance(nested, dict):
            nested = {}
            table[part] = nested
        table = nested
    table[parts[-1]] = dict(values)

    cfg[CONFIG_VERSION_KEY] = CONFIG_VERSION
    with path.open("wb") as handle:
        tomli_w.dump(cfg, handle)


def _attend_mode(value: Any, fallback: str) -> str:
    text = str(value).strip().lower() if value is not None else ""
    return text if text in _ATTEND_MODES else fallback


def resolve_attend_settings(cfg: dict[str, Any] | None = None) -> AttendSettings:
    """The effective attendant settings: the config wins, the environment is the fallback.

    Three tiers per key — the config value when the key is present, else the environment
    variable when it is set, else the built-in default. So a machine that has never
    opened the settings pane keeps the behaviour its ``GROOM_ATTEND`` export gave it, and
    the first save takes ownership of the key for good.
    """
    data = cfg if cfg is not None else load_config()
    table = get_config_value(ATTEND_SECTION, data)
    section: dict[str, Any] = table if isinstance(table, dict) else {}
    sources: dict[str, str] = {}

    env_mode = os.environ.get(ATTEND_MODE_ENV)
    if "mode" in section:
        mode = _attend_mode(section.get("mode"), ATTEND_OFF)
        sources["mode"] = CONFIG_SOURCE
    elif env_mode is not None:
        mode = _attend_mode(env_mode, ATTEND_OFF)
        sources["mode"] = ENV_SOURCE
    else:
        mode = ATTEND_OFF
        sources["mode"] = DEFAULT_SOURCE

    if "last_mode" in section:
        last_mode = _attend_mode(section.get("last_mode"), ATTEND_HEADLESS)
        sources["last_mode"] = CONFIG_SOURCE
    elif mode != ATTEND_OFF:
        # Never configured, but running: whatever is running is what a toggle should
        # restore.
        last_mode = mode
        sources["last_mode"] = sources["mode"]
    else:
        last_mode = ATTEND_HEADLESS
        sources["last_mode"] = DEFAULT_SOURCE
    if last_mode == ATTEND_OFF:
        last_mode = ATTEND_HEADLESS

    env_cli = os.environ.get(ATTEND_CLI_ENV)
    raw_cli = section.get("cli")
    if isinstance(raw_cli, str) and raw_cli.strip():
        cli = raw_cli.strip()
        sources["cli"] = CONFIG_SOURCE
    elif env_cli is not None and env_cli.strip():
        cli = env_cli.strip()
        sources["cli"] = ENV_SOURCE
    else:
        cli = BUILTIN_ATTEND_CLI
        sources["cli"] = DEFAULT_SOURCE

    raw_deny = section.get("deny")
    if isinstance(raw_deny, list):
        deny = tuple(str(item).strip().lower() for item in raw_deny if str(item).strip())
        sources["deny"] = CONFIG_SOURCE
    elif os.environ.get(ATTEND_DENY_ENV):
        raw_env = os.environ.get(ATTEND_DENY_ENV, "")
        deny = tuple(part.strip().lower() for part in raw_env.split(",") if part.strip())
        sources["deny"] = ENV_SOURCE
    else:
        deny = ()
        sources["deny"] = DEFAULT_SOURCE

    return AttendSettings(
        mode=mode, last_mode=last_mode, cli=cli, deny=deny, sources=sources
    )


def write_attend_settings(settings: AttendSettings) -> None:
    """Persist the whole ``[groom.attend]`` table from a resolved settings object."""
    write_config_section(
        ATTEND_SECTION,
        {
            "mode": settings.mode,
            "last_mode": settings.last_mode,
            "cli": settings.cli,
            "deny": list(settings.deny),
        },
    )
