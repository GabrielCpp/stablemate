"""The repository a person works in: the watched files it holds."""

from __future__ import annotations

from datetime import date
from typing import cast

from ostler.book import Collection, State, Unique

from .files import CONFIG, USER_LIBRARY, FileRecord, holding


class Repo(State):
    files = Collection(FileRecord, Unique("path"))

    def __init__(self, today: date):
        super().__init__(today)
        self.files.items[CONFIG] = holding(CONFIG)

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: f.path))

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)


def stage(model: Repo) -> str:
    """How far the repository has come: the scene it is in."""
    config = model.files.get("agents.yml")
    if config is None:
        return "user-library" if USER_LIBRARY in model.files[CONFIG].holds else "bare"
    if ".agents/agents.mk" in model.files:
        return "installed"
    if "- demo" in config.holds:
        return "selected"
    return "hand-configured" if "# hand-written" in config.holds else "initialized"
