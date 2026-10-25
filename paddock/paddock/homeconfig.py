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


def _anchored(value: object, stage: Path) -> str | None:
    """The absolute path inside *stage* that a relative path names, or None when *value* is not one."""
    if not isinstance(value, str) or not value or value.startswith("~") or Path(value).is_absolute():
        return None
    return str((stage / value).resolve())


def _anchor_artifacts_dir(config: TomlTable, stage: Path) -> bool:
    anchored = _anchored(config.get("artifacts_dir"), stage)
    if anchored is None:
        return False
    config["artifacts_dir"] = anchored
    return True


def _anchor_workspaces(config: TomlTable, stage: Path) -> bool:
    """Rewrite each relative `[workspaces]` member to its path inside *stage*; malformed shapes are left for core to report."""
    workspaces = config.get("workspaces")
    if not isinstance(workspaces, dict):
        return False
    changed = False
    for members in cast(dict[str, object], workspaces).values():
        if not isinstance(members, list):
            continue
        entries = cast(list[object], members)
        for index, entry in enumerate(entries):
            if isinstance(entry, dict):
                table = cast(TomlTable, entry)
                anchored = _anchored(table.get("path"), stage)
                if anchored is not None:
                    table["path"] = anchored
                    changed = True
                continue
            anchored = _anchored(entry, stage)
            if anchored is not None:
                entries[index] = anchored
                changed = True
    return changed


def materialize(base: Path, override: Mapping[str, object], dest: Path, *, stage: Path) -> Path:
    """Write the config a run uses to *dest*: the benchmark's base, with the task's override laid over it.

    A relative `artifacts_dir`, and a relative path in a `[workspaces]` entry, name a folder inside *stage*
    and are written as that absolute path.
    With no override and nothing to rewrite the base file is copied byte for byte.
    """
    parsed = load(base)
    dest.parent.mkdir(parents=True, exist_ok=True)
    merged = deep_merge(parsed, override) if override else parsed
    artifacts = _anchor_artifacts_dir(merged, stage)
    members = _anchor_workspaces(merged, stage)
    rewritten = artifacts or members
    if not override and not rewritten:
        _ = shutil.copyfile(base, dest)
        return dest
    _ = dest.write_text(tomli_w.dumps(merged), encoding="utf-8")
    return dest
