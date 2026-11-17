"""The directory a person works in: the watched files it holds."""

from __future__ import annotations

from typing import cast

from ostler.book import Collection, State, Unique

from .files import FileRecord


class Workspace(State):
    files = Collection(FileRecord, Unique("path"))

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: f.path))

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)


def skills_installed(model: Workspace) -> bool:
    return ".claude/skills/ostler-book/SKILL.md" in model.files


def scaffolded(model: Workspace) -> bool:
    return "fix-tests/pyproject.toml" in model.files


def programmed(model: Workspace) -> bool:
    return "specs/demo/program.yml" in model.files


def stage(model: Workspace) -> str:
    """How far the directory has come: the scene it is in."""
    if scaffolded(model):
        return "scaffolded with skills" if skills_installed(model) else "scaffolded"
    if skills_installed(model):
        return "skills installed"
    return "program written" if programmed(model) else "bare"
