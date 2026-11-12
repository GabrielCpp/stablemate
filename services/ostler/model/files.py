"""The files the book watches and what the model keeps for each: its path and
which of the declared strings it holds. A row is that and nothing more."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import ClassVar

from ostler.book import Mark

from ..fixtures import EPICS, STORY_PATHS

NOT_STARTED = "status: Not started"
IN_PROGRESS = "status: in-progress"
BLOCKED = "status: 'Blocked: waiting'"
STATUS_LINES = {"Not started": NOT_STARTED, "in-progress": IN_PROGRESS, "Blocked: waiting": BLOCKED}
CONFLICT_TEXTS = ("criteria disagree", "specs contradict")
CONFLICT_LINES = tuple(f"conflict: {t}" for t in CONFLICT_TEXTS)
SEED_IDS = ("SD-3", "SD-4")
SEED_STATUSES = ("backlog", "researched")
SEED_LAYERS = (None, "frontend")


def seed_block(seed_id: str, status: str, layer: str | None) -> str:
    """The block `seed add` leaves under Seeds: heading, status line, the layers line when there is one, a blank line."""
    layers = f"- layers: {layer}\n" if layer else ""
    return f"### {seed_id}\n- status: {status}\n{layers}\n"


SEED_BLOCKS = tuple(seed_block(i, s, layer) for i in SEED_IDS for s in SEED_STATUSES for layer in SEED_LAYERS)

MARKS = (
    Mark("art/epics/*/stories/*/story.md", NOT_STARTED, IN_PROGRESS, BLOCKED, *CONFLICT_LINES),
    Mark("art/epics/*/epic.md", *SEED_BLOCKS),
)

EPIC_PATHS = tuple(f"art/epics/{e}/epic.md" for e in EPICS)
STORY_FILES = tuple(STORY_PATHS.values())


@dataclass(frozen=True)
class FileRecord:
    """A watched file the sandbox holds."""

    path: str
    holds: tuple[str, ...] = ()

    source: ClassVar[tuple[str, ...]] = ("ostler/ostler/crud.py::set_status", "ostler/ostler/crud.py::add_seed")

    def __str__(self) -> str:
        return f"{self.path} [{'; '.join(self.holds)}]"


def declared(path: str) -> tuple[str, ...]:
    """The strings the watch looks for in this path, in the order it lists them."""
    return tuple(dict.fromkeys(s for m in MARKS if fnmatch.fnmatchcase(path, m.glob) for s in m.holds))


def holding(path: str, *strings: str) -> FileRecord:
    """The record of a file that holds these strings, in the order the watch lists them."""
    return FileRecord(path, tuple(s for s in declared(path) if s in strings))
