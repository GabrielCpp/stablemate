"""The plan repository a person works in: the queue of epics and the watched files it holds."""

from __future__ import annotations

from datetime import date
from typing import cast

from ostler.book import Collection, State, Unique

from ..fixtures import ALPHA, STORY_PATHS, slug_of
from .files import (CONFLICT_LINES, EPIC_PATHS, NOT_STARTED, SEED_IDS, STATUS_LINES, STORY_FILES, FileRecord,
                    holding)
from .records import Queue

SEEDED_QUEUE = ("0001-first", "0002-second")
QUEUE = "epics"
SECOND_EPIC = "art/epics/0002-second/epic.md"


class Plan(State):
    files = Collection(FileRecord, Unique("path"))
    queue = Collection(Queue, Unique("name"))

    def __init__(self, today: date):
        super().__init__(today)
        for path in STORY_FILES:
            self.files.items[path] = holding(path, NOT_STARTED)
        for path in EPIC_PATHS:
            self.files.items[path] = holding(path)
        self.queue.items[QUEUE] = Queue(QUEUE, SEEDED_QUEUE)

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: f.path))

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)

    def epics(self) -> tuple[str, ...]:
        return self.queue[QUEUE].epics


def queue_stage(model: Plan) -> str:
    """How the queue stands: its epics by slug, first to last."""
    return " > ".join(slug_of(e) for e in model.epics()) or "empty"


def story_stage(model: Plan) -> str:
    """Where the story alpha stands: its status, and whether a conflict is recorded on it."""
    held = model.files[STORY_PATHS[ALPHA]].holds
    status = next(name for name, line in STATUS_LINES.items() if line in held)
    return f"{status} with conflict" if any(line in held for line in CONFLICT_LINES) else status


def seed_stage(model: Plan) -> str:
    """Which seeds the epic 0002-second lists."""
    held = model.files[SECOND_EPIC].holds
    found = [i for i in SEED_IDS if any(b.startswith(f"### {i}\n") for b in held)]
    return " + ".join(found) or "no seeds"
