from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir


CONFIG_PATH_ENV = "WORKHORSE_CONFIG"


def _default_config_path() -> Path:
    """Resolve the platform-appropriate config directory for workhorse.

    ~/Library/Application Support/workhorse on macOS, %APPDATA%\\workhorse on Windows,
    ~/.config/workhorse on Linux."""
    return Path(user_config_dir("workhorse")) / "config.toml"


@dataclass(frozen=True)
class PowerMapping:
    model: str | None = None
    effort: str | None = None


def config_path() -> Path:
    raw = os.environ.get(CONFIG_PATH_ENV)
    if raw:
        return Path(raw).expanduser()
    return _default_config_path()


def write_config_key(key: str, value: str) -> None:
    """Persist a single top-level string key, preserving all other keys."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg[key] = value
    lines = []
    for k, v in cfg.items():
        escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{k} = "{escaped}"\n')
    path.write_text("".join(lines), encoding="utf-8")


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text())


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
