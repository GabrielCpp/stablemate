"""The code held to the strict gate: the paths in `[tool.stablemate.strict]`."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class ScopeError(Exception):
    pass


@dataclass(frozen=True)
class StrictScope:
    paths: tuple[str, ...]
    max_lines: int

    def contains(self, rel_path: str) -> bool:
        return any(rel_path == root or rel_path.startswith(f"{root}/") for root in self.paths)


def _strict_table(pyproject: object) -> object:
    table = pyproject
    for key in ("tool", "stablemate", "strict"):
        table = table.get(key) if isinstance(table, dict) else None
    return table


def load(repo: Path) -> StrictScope:
    with (repo / "pyproject.toml").open("rb") as handle:
        table = _strict_table(tomllib.load(handle))
    if not isinstance(table, dict):
        raise ScopeError("pyproject.toml has no [tool.stablemate.strict] table")
    paths = table.get("paths")
    max_lines = table.get("max-lines")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise ScopeError(f"[tool.stablemate.strict] paths must be a list of strings, got {paths!r}")
    if not isinstance(max_lines, int):
        raise ScopeError(f"[tool.stablemate.strict] max-lines must be an integer, got {max_lines!r}")
    return StrictScope(paths=tuple(str(path) for path in paths), max_lines=max_lines)
