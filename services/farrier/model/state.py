"""The repository a person works in: the watched files it holds."""

from __future__ import annotations

from typing import cast

from ostler.book import Collection, State, Unique

from .files import FileRecord


class Repo(State):
    files = Collection(FileRecord, Unique("path"))

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: f.path))

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)


def stage(model: Repo) -> str:
    """How far the repository has come: the scene it is in."""
    config = model.files.get("agents.yml")
    if config is None:
        return "bare"
    if ".agents/agents.mk" in model.files:
        return "installed"
    if "- demo" in config.holds:
        return "selected"
    return "hand-configured" if "# hand-written" in config.holds else "initialized"
