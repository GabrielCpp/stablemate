"""Home-config persistence, shared by every stablemate tool.

One file, ``~/.config/stablemate/config.toml`` (platform-appropriate), read and
written by workhorse and farrier alike. It used to be one file *per tool*, which meant
``workhorse config set-base`` and ``farrier config set-base`` wrote to different places
and could silently disagree about ``library_dir`` / ``stablemate_dir`` / ``base_dir`` —
keys that only mean anything if every tool sees the same value.

Legacy per-tool files are still read when the unified one is absent, and the first
write migrates them, so an existing setup keeps working without a manual step.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_dir

CONFIG_PATH_ENV = "STABLEMATE_CONFIG"
# The pre-unification override. Honored so an existing WORKHORSE_CONFIG export keeps
# pointing at the file its owner meant.
LEGACY_CONFIG_PATH_ENV = "WORKHORSE_CONFIG"

# Per-tool files predating the unified one. Read (merged, in order) when no unified
# config exists; the next write folds them into one. farrier's is listed here on
# purpose: these keys are shared, so workhorse inheriting a farrier-configured
# `library_dir` is the point, not a leak.
_LEGACY_APPS = ("workhorse", "farrier")


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


def load_config() -> dict[str, Any]:
    """The effective config: the unified file, else the merged legacy per-tool files.

    The legacy fallback applies ONLY to the default path. An explicitly named config
    ($STABLEMATE_CONFIG) that happens not to exist means "this file", not "and also
    whatever is in ~/.config/workhorse" — silently reading another file would ignore
    what the caller asked for, and makes the env var useless for isolating a run.
    """
    path = config_path()
    if path.is_file():
        return _read(path)
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
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg[key] = value
    with path.open("wb") as handle:
        tomli_w.dump(cfg, handle)


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
