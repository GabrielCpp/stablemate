"""The shelf a person's secrets sit on, and the files around it."""

from __future__ import annotations

from datetime import date

from ostler.book import Collection, State, Unique

from .files import BROKEN, CONFIG, DOTENV, EXPORT, FOREIGN, INITIAL_DOTENV, FileRecord
from .records import SecretRecord


class Store(State):
    secrets = Collection(SecretRecord, Unique("name"))
    files = Collection(FileRecord, Unique("path"))

    def __init__(self, today: date):
        super().__init__(today)
        self.files.items[CONFIG] = FileRecord.holding(CONFIG)
        self.files.items[DOTENV] = FileRecord.holding(DOTENV, *INITIAL_DOTENV)
        self.files.items[EXPORT] = FileRecord.holding(EXPORT, "saddlebag-export")
        self.files.items[BROKEN] = FileRecord.holding(BROKEN, "{")
        self.files.items[FOREIGN] = FileRecord.holding(FOREIGN, '"x": 1')

    def rows(self) -> tuple[object, ...]:
        return tuple(sorted(self.secrets, key=lambda r: r.name)) + tuple(sorted(self.files, key=lambda f: f.path))

    def row(self, entity: object) -> object:
        return entity
