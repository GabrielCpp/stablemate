"""The operator's standing choice of route: an environment variable, else the shared stablemate config file."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs
from pydantic import ValidationError

from saddlebag._vendor.stablemate_core.config import ConfigError, load_home_config
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


def _bad_backend(exc: ConfigError) -> object | None:
    cause = exc.__cause__
    if not isinstance(cause, ValidationError):
        return None
    for error in cause.errors():
        if error["loc"] == (TABLE, KEY):
            return error["input"]
    return None


def read(environ: Mapping[str, str] = os.environ) -> Preference | None:
    """The operator's preference, or None when neither the environment nor the config file states one."""
    value = environ.get(ENV)
    if value is not None:
        if value not in CHOICES:
            raise RouteError(f"unknown {ENV} {value!r}: expected keyring or daemon")
        return Preference(value, ENV)
    path = config_path(environ)
    try:
        home = load_home_config(path)
    except ConfigError as exc:
        bad = _bad_backend(exc)
        if bad is not None:
            raise RouteError(f"unknown backend {bad!r} in [{TABLE}] of {path}: expected keyring or daemon") from exc
        raise RouteError(f"cannot read {path}: {exc}") from exc
    chosen = home.saddlebag.backend if home.saddlebag is not None else None
    return None if chosen is None else Preference(chosen, str(path))
