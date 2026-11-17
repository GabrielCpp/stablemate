"""The plan repository a person works in: the queue of epics and the watched files it holds."""

from __future__ import annotations

import re
from datetime import date
from typing import cast

from ostler.book import Collection, State, Unique

from ..fixtures import ALPHA, SLUGS, STORY_PATHS, slug_of
from .files import (BULLET_LINES, CONFLICT_LINES, EPIC_PATHS, NOT_STARTED, SEED_IDS, STATUS_LINES, STORY_FILES,
                    FileRecord, holding, OLD_BULLET, OLD_LIST)
from .records import Queue

_NUMBERED = re.compile(r"^(\d{4,})-(.+)$")
SEEDED_QUEUE = ("0001-first", "0002-second")
QUEUE = "epics"
SECOND_EPIC = "art/epics/0002-second/epic.md"


class Plan(State):
    files = Collection(FileRecord, Unique("path"))
    queue = Collection(Queue, Unique("name"))

    def __init__(self, today: date):
        super().__init__(today)
        for path in STORY_FILES:
            self.files.items[path] = holding(path, NOT_STARTED, BULLET_LINES["Not started"])
        for path in EPIC_PATHS:
            epic = path.split("/")[2]
            listed = [(sid, STORY_PATHS[sid]) for sid in STORY_PATHS if STORY_PATHS[sid].startswith(f"art/epics/{epic}/")]
            held = [m for sid, _ in listed for m in (f"### {SLUGS[sid]}", f"- title: Story {SLUGS[sid]}")]
            self.files.items[path] = holding(path, *held)
        self.files.items[OLD_LIST] = holding(OLD_LIST, OLD_BULLET)
        self.queue.items[QUEUE] = Queue(QUEUE, SEEDED_QUEUE)

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: tuple(f.path.split("/"))))

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)

    def epics(self) -> tuple[str, ...]:
        return self.queue[QUEUE].epics

    def epic_dirs(self) -> tuple[str, ...]:
        """The epic folders that hold an epic.md, in name order."""
        return tuple(sorted(f.path.split("/")[2] for f in self.files if f.path.endswith("/epic.md")))

    def resolve_epic(self, name: str) -> str:
        """The folder an epic name stands for: as typed when it exists or carries a number, else the epic with that slug."""
        name = name.strip()
        dirs = self.epic_dirs()
        if not name or name in dirs or _NUMBERED.match(name):
            return name
        return next((d for d in dirs if slug_of(d) == name), name)

    def has_story(self, story: str) -> bool:
        return story in STORY_PATHS and STORY_PATHS[story] in self.files.items


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


def plan_stage(model: Plan) -> str:
    """Which stories each epic holds, epic by epic."""
    stories = sorted(f.path for f in model.files if "/stories/" in f.path)
    return " ".join(
        f"{slug_of(e)}({','.join(p.split('/')[4] for p in stories if p.split('/')[2] == e)})" for e in model.epic_dirs())
