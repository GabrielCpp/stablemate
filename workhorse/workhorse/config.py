from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONFIG_PATH_ENV = "WORKHORSE_CONFIG"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "workhorse" / "config.toml"


@dataclass(frozen=True)
class PowerMapping:
    model: str | None = None
    effort: str | None = None


def config_path() -> Path:
    raw = os.environ.get(CONFIG_PATH_ENV)
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_CONFIG_PATH


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text())


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
    model = backend_table.get("model")
    effort = backend_table.get("effort")
    return PowerMapping(
        model=model if isinstance(model, str) and model else None,
        effort=effort if isinstance(effort, str) and effort else None,
    )


def get_config_value(name: str, cfg: dict[str, Any] | None = None) -> Any:
    data = cfg if cfg is not None else load_config()
    value: Any = data
    for part in name.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value
