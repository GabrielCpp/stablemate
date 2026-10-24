"""The home config a run uses in place of the maintainer's: a benchmark's base, laid over by a task."""

from __future__ import annotations

import shutil
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import tomli_w

TomlTable = dict[str, object]


class HomeConfigError(RuntimeError):
    """A benchmark's base config that cannot be read."""


def deep_merge(base: Mapping[str, object], override: Mapping[str, object]) -> TomlTable:
    """*base* with *override* laid over it. Tables merge key by key, any other value is replaced."""
    merged: TomlTable = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(cast(Mapping[str, object], current), cast(Mapping[str, object], value))
        else:
            merged[key] = value
    return merged


def load(path: Path) -> TomlTable:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HomeConfigError(f"{path} cannot be read ({exc.strerror})") from exc
    except tomllib.TOMLDecodeError as exc:
        raise HomeConfigError(f"{path} is not TOML ({exc})") from exc


def materialize(base: Path, override: Mapping[str, object], dest: Path) -> Path:
    """Write the config a run uses to *dest*: the benchmark's base, with the task's override laid over it.

    With no override the base file is copied byte for byte.
    """
    parsed = load(base)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not override:
        _ = shutil.copyfile(base, dest)
        return dest
    _ = dest.write_text(tomli_w.dumps(deep_merge(parsed, override)), encoding="utf-8")
    return dest
