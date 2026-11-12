"""What a user types after the command name, as the model reads it. A field is
named as the argument is, and left None where the user leaves the flag out."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from ostler.book import Actor, Fixture

EPICS = ("0001-first", "0002-second", "0003-third")
ALPHA = "TST-01M585P7WKBH9YJ8E6NA73W4S9"
BRAVO = "TST-01M585P8MYP5WJAMJ89Z981GEG"
SX = "TST-01M585PFWZZXH4Y6KNMH1VK58H"
STORY_PATHS = {
    ALPHA: "art/epics/0001-first/stories/alpha/story.md",
    BRAVO: "art/epics/0001-first/stories/bravo/story.md",
    SX: "art/epics/0002-second/stories/sx/story.md",
}
SEED_STATUSES = ("backlog", "researched", "covered", "resolved", "dropped", "deferred")
SEED_LAYERS = ("frontend", "backend", "infra")
_NUMBERED = re.compile(r"^(\d{4,})-(.+)$")


def slug_of(name: str) -> str:
    """The slug half of an epic name: the whole name when it carries no number."""
    found = _NUMBERED.match(name.strip())
    return found.group(2) if found else name.strip()


def directory_of(name: str) -> str:
    """The directory an epic name stands for: a numbered name as typed, a bare slug as the epic that has it."""
    name = name.strip()
    if _NUMBERED.match(name):
        return name
    return next((e for e in EPICS if slug_of(e) == name), name)


class Epic:
    """An epic a user names, by its number and slug or by the slug alone."""

    name: str | None

    @property
    def canonical(self) -> str:
        return directory_of(self.name or "")


@dataclass
class AddArgs(Epic, Fixture):
    name: str | None = None
    front: bool | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[AddArgs]:
        return (todo_add("third"), todo_add("0003-third", front=True), todo_add("second"), todo_add("0009-nope"))


@dataclass
class PruneArgs(Epic, Fixture):
    name: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[PruneArgs]:
        return (todo_prune("second"), todo_prune("0003-third"), todo_prune("0001-first"))


@dataclass
class ReorderArgs(Fixture):
    first: str | None = None
    then: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[ReorderArgs]:
        return (todo_reorder("second"), todo_reorder("0002-second", "0001-first"), todo_reorder("0001-first", "0003-third"))


@dataclass
class ListArgs(Fixture):
    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[ListArgs]:
        return (todo_list(),)


@dataclass
class SeedAddArgs(Fixture):
    epic: str | None = None
    seed: str | None = None
    status: str | None = None
    layer: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[SeedAddArgs]:
        return (seed_add(), seed_add("0002-second", "SD-4", status="researched", layer="frontend"), seed_add("0009"),
                seed_add(status="weird"), seed_add(layer="cloud"))


@dataclass
class SeedRemoveArgs(Fixture):
    epic: str | None = None
    seed: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[SeedRemoveArgs]:
        return (seed_remove(), seed_remove("0002-second", "SD-4"), seed_remove("0009"))


@dataclass
class SetStatusArgs(Fixture):
    story: str | None = None
    status: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[SetStatusArgs]:
        return (set_status(), set_status(ALPHA, "Blocked: waiting"), set_status(ALPHA, "Not started"), set_status("TST-NOPE"))


@dataclass
class ConflictArgs(Fixture):
    story: str | None = None
    text: str | None = None
    clear: bool | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[ConflictArgs]:
        return (conflict(), conflict(ALPHA, "specs contradict"), conflict(ALPHA, None, clear=True), conflict(ALPHA, None),
                conflict(ALPHA, "criteria disagree", clear=True), conflict("TST-NOPE"))


@dataclass
class PathEpicArgs(Fixture):
    name: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[PathEpicArgs]:
        return (path_epic(), path_epic("first"), path_epic("nope"))


def todo_add(name: str | None = "third", *, front: bool | None = None) -> AddArgs:
    return AddArgs(name=name, front=front)


def todo_prune(name: str | None = "0002-second") -> PruneArgs:
    return PruneArgs(name=name)


def todo_reorder(first: str | None = "0002-second", then: str | None = None) -> ReorderArgs:
    return ReorderArgs(first=first, then=then)


def todo_list() -> ListArgs:
    return ListArgs()


def seed_add(epic: str | None = "0002-second", seed: str | None = "SD-3", *, status: str | None = None,
             layer: str | None = None) -> SeedAddArgs:
    return SeedAddArgs(epic=epic, seed=seed, status=status, layer=layer)


def seed_remove(epic: str | None = "0002-second", seed: str | None = "SD-3") -> SeedRemoveArgs:
    return SeedRemoveArgs(epic=epic, seed=seed)


def set_status(story: str | None = ALPHA, status: str | None = "in-progress") -> SetStatusArgs:
    return SetStatusArgs(story=story, status=status)


def conflict(story: str | None = ALPHA, text: str | None = "criteria disagree", *, clear: bool | None = None) -> ConflictArgs:
    return ConflictArgs(story=story, text=text, clear=clear)


def path_epic(name: str | None = "0001-first") -> PathEpicArgs:
    return PathEpicArgs(name=name)


__all__ = [
    "ALPHA", "AddArgs", "BRAVO", "ConflictArgs", "EPICS", "ListArgs", "PathEpicArgs", "PruneArgs", "ReorderArgs", "SEED_LAYERS",
    "SEED_STATUSES", "STORY_PATHS", "SX", "SeedAddArgs", "SeedRemoveArgs", "SetStatusArgs", "conflict", "directory_of", "path_epic",
    "seed_add", "seed_remove", "set_status", "slug_of", "todo_add", "todo_list", "todo_prune", "todo_reorder",
]
