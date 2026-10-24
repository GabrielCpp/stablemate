"""The operator's standing choice of route: an environment variable, else the shared stablemate config file."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from saddlebag.store import RouteError

ENV = "SADDLEBAG_BACKEND"
CONFIG_PATH_ENV = "STABLEMATE_CONFIG"
TABLE = "saddlebag"
KEY = "backend"
CHOICES = ("keyring", "daemon")


def config_path(environ: Mapping[str, str] = os.environ) -> Path:
    """The shared stablemate config file: $STABLEMATE_CONFIG, else platformdirs' user config dir."""
    explicit = environ.get(CONFIG_PATH_ENV)
    if explicit:
        return Path(explicit).expanduser()
    return Path(platformdirs.user_config_dir("stablemate")) / "config.toml"


@dataclass(frozen=True)
class Preference:
    """A chosen route and where the choice was read from."""

    backend: str
    source: str


def read(environ: Mapping[str, str] = os.environ) -> Preference | None:
    """The operator's preference, or None when neither the environment nor the config file states one."""
    value = environ.get(ENV)
    if value is not None:
        if value not in CHOICES:
            raise RouteError(f"unknown {ENV} {value!r}: expected keyring or daemon")
        return Preference(value, ENV)
    path = config_path(environ)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        table = tomllib.loads(text).get(TABLE)
    except tomllib.TOMLDecodeError as exc:
        raise RouteError(f"cannot read {path}: {exc}") from exc
    chosen = table.get(KEY) if isinstance(table, dict) else None
    if not isinstance(chosen, str):
        return None
    if chosen not in CHOICES:
        raise RouteError(f"unknown backend {chosen!r} in [{TABLE}] of {path}: expected keyring or daemon")
    return Preference(chosen, str(path))
