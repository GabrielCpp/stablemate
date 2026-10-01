"""The skill reference helpers every stablemate tool renders a template with."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "MissingSkill",
    "SkillCatalog",
    "SkillEntry",
    "SkillRefs",
    "display_path",
]

SLASH_HARNESSES = frozenset({"claude", "copilot"})
DOLLAR_HARNESSES = frozenset({"codex"})


class MissingSkill(LookupError):
    """A named reference that no catalog entry answers."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"no installed skill or prompt is named {self.name!r}"


@dataclass(frozen=True)
class SkillEntry:
    """One skill or prompt the harness will load, keyed by its library name."""

    name: str
    installed: str
    path: Path
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillCatalog:
    """The entries a render resolves against, the most local first."""

    entries: tuple[SkillEntry, ...] = ()
    _by_name: dict[str, SkillEntry] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_name: dict[str, SkillEntry] = {}
        for entry in self.entries:
            by_name.setdefault(entry.name, entry)
        object.__setattr__(self, "_by_name", by_name)

    @classmethod
    def of(cls, entries: Iterable[SkillEntry]) -> SkillCatalog:
        return cls(tuple(entries))

    def get(self, name: str) -> SkillEntry | None:
        return self._by_name.get(name)

    def tagged(self, tags: Iterable[str]) -> list[SkillEntry]:
        """The entries carrying every one of *tags*, by name, each name once."""
        wanted = {tag.lower() for tag in tags}
        if not wanted:
            return []
        return sorted(
            (entry for entry in self._by_name.values() if wanted <= set(entry.tags)),
            key=lambda entry: entry.name,
        )


def display_path(path: Path, *, base: Path, root: Path, home: Path) -> str:
    """*path* relative to *base* when it sits under *root*, else from the home folder."""
    if path.is_relative_to(root):
        return os.path.relpath(path, base).replace(os.sep, "/")
    if path.is_relative_to(home):
        return f"~/{path.relative_to(home).as_posix()}"
    return path.as_posix()


@dataclass(frozen=True)
class SkillRefs:
    """The template helpers for one rendered file, bound to its catalog and harness."""

    catalog: SkillCatalog
    harness: str
    base: Path
    root: Path
    home: Path
    on_missing: Callable[[str], str] | None = None

    def _resolve(self, name: str) -> SkillEntry | str:
        entry = self.catalog.get(name)
        if entry is not None:
            return entry
        if self.on_missing is None:
            raise MissingSkill(name)
        return self.on_missing(name)

    def _show(self, path: Path) -> str:
        return display_path(path, base=self.base, root=self.root, home=self.home)

    def _link(self, entry: SkillEntry) -> str:
        return f"[{entry.installed}]({self._show(entry.path)})"

    def skill_link(self, name: str) -> str:
        found = self._resolve(name)
        return found if isinstance(found, str) else self._link(found)

    def skill_path(self, name: str, relative: str = "") -> str:
        found = self._resolve(name)
        if isinstance(found, str):
            return found
        path = found.path.parent / relative if relative else found.path
        return self._show(path)

    def skill_command(self, name: str) -> str:
        found = self._resolve(name)
        if isinstance(found, str):
            return found
        if self.harness in SLASH_HARNESSES:
            return f"/{found.installed}"
        if self.harness in DOLLAR_HARNESSES:
            return f"${found.installed}"
        return f"Read `{self._show(found.path)}` and follow its instructions"

    def find_by_tags(self, *tags: str) -> str:
        return ", ".join(self._link(entry) for entry in self.catalog.tagged(tags))

    def has_skill(self, name: str) -> bool:
        return self.catalog.get(name) is not None

    def globals(self) -> dict[str, Any]:
        """The helpers by the names a template calls them."""
        return {
            "skill_link": self.skill_link,
            "skill_path": self.skill_path,
            "skill_command": self.skill_command,
            "find_by_tags": self.find_by_tags,
            "has_skill": self.has_skill,
        }
