"""Home-config persistence, shared by every stablemate tool.

One file, ``~/.config/stablemate/config.toml`` (platform-appropriate), read and
written by workhorse and farrier alike. It used to be one file *per tool*, which meant
``workhorse config set-base`` and ``farrier config set-base`` wrote to different places
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
import os
import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
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

# The schema this build reads and writes. v1 is the unified config.toml — one file for
# every tool, replacing the per-tool ones.
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
CONFIG_VERSION = 1

CONFIG_VERSION_KEY = "config_version"

# Steps that carry a config forward one schema version: _MIGRATIONS[n] takes a v(n)
# config and returns a v(n+1) one. Empty while CONFIG_VERSION is 1 — there is no older
# schema to come from. When v2 lands, add the v1->v2 step here and a row above; the walk
# in _migrate_forward needs no change.
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class ConfigVersionError(RuntimeError):
    """A config this build must not touch — it was written by a newer stablemate-core.

    Raised on WRITE, never on read. Writing is where the damage happens: a writer
    serializes the whole file back, so one that does not understand a key drops or
    mangles it. That is not hypothetical here — it is the bug this module was created
    to fix, where a hand-rolled writer stringified a table it did not understand and
    every node silently fell back to the default model, with no error anywhere.
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
    """
    path = config_path()
    if path.is_file():
        data = _read(path)
        _warn_if_too_new(data)
        return data
    if _path_is_explicit():
        return {}

    merged: dict[str, Any] = {}
    for legacy in legacy_config_paths():
        merged.update(_read(legacy))
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
    :data:`CONFIG_VERSION`. This is the one guard that holds no matter how the tools were
    installed — two pipx venvs, two vendored copies, one shared venv — because it defends
    the file rather than trusting the code that reaches it. An older config is carried
    forward first, so a write never mixes schemas.
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config()

    found = config_version_of(cfg)
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

    data = dict(cfg)
    for version in range(from_version, CONFIG_VERSION):
        step = _MIGRATIONS.get(version)
        if step is None:
            raise ConfigVersionError(
                f"no migration registered from config schema v{version} to "
                f"v{version + 1}; {path} cannot be carried forward safely."
            )
        data = step(data)
    return data


def _mapping_from_table(table: dict[str, Any]) -> PowerMapping:
    model = table.get("model")
    effort = table.get("effort")
    return PowerMapping(
        model=model if isinstance(model, str) and model else None,
        effort=effort if isinstance(effort, str) and effort else None,
    )


def resolve_power(power: str | None, backend: str, cfg: dict[str, Any] | None = None) -> PowerMapping:
    if not power:
        return PowerMapping()
    data = cfg if cfg is not None else load_config()
    power_table = data.get("power")
    if not isinstance(power_table, dict):
        return PowerMapping()
    level_table = power_table.get(power)
    if not isinstance(level_table, dict):
        return PowerMapping()
    backend_table = level_table.get(backend) or level_table.get("default")
    if not isinstance(backend_table, dict):
        return PowerMapping()
    return _mapping_from_table(backend_table)


def resolve_backend_default(backend: str, cfg: dict[str, Any] | None = None) -> PowerMapping:
    """Per-backend default model/effort from the top-level ``[default.<backend>]`` table.

    The configurable counterpart of a backend's hardcoded ``default_model``: it fills
    whatever a node's power tier (or the absence of one) left unset, so power-less
    nodes stop silently falling through to the harness's own default model. Missing
    table/backend sections yield an empty mapping, never an error.
    """
    data = cfg if cfg is not None else load_config()
    default_table = data.get("default")
    if not isinstance(default_table, dict):
        return PowerMapping()
    backend_table = default_table.get(backend)
    if not isinstance(backend_table, dict):
        return PowerMapping()
    return _mapping_from_table(backend_table)


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


def resolve_stablemate_dir() -> Path | None:
    """The configured stablemate checkout path, or None if unset."""
    configured = get_config_value("stablemate_dir")
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser().resolve()
    return None
