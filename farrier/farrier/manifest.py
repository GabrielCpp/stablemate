"""The repository manifest as farrier reads it: a loaded :class:`Manifest`, or a mapping checked into one."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from farrier._vendor.stablemate_core.config import ConfigError
from farrier._vendor.stablemate_core.manifest import (
    MANIFEST_NAME,
    find_manifest,
    locate_manifest,
    load_manifest,
    parse_manifest,
)
from farrier._vendor.stablemate_core.schema import Manifest

__all__ = [
    "ConfigLike",
    "MANIFEST_NAME",
    "as_manifest",
    "excluded",
    "find_manifest",
    "locate_manifest",
    "read_manifest",
]

ConfigLike = Manifest | Mapping[str, Any]


def as_manifest(config: ConfigLike) -> Manifest:
    """*config* as a :class:`Manifest`, checking a mapping once; a bad manifest exits with its key paths."""
    if isinstance(config, Manifest):
        return config
    try:
        return parse_manifest(config, Path(MANIFEST_NAME))
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc


def read_manifest(path: Path) -> Manifest:
    """The manifest at *path*, loaded and checked; a bad one exits with its key paths."""
    try:
        return load_manifest(path)
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc


def excluded(config: ConfigLike, kind: str) -> set[str]:
    """The ``exclude:`` entries of *config* for *kind*, ``skills`` or ``prompts``."""
    table = as_manifest(config).exclude
    if table is None:
        return set()
    return set(table.skills if kind == "skills" else table.prompts)
