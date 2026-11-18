"""The epics queue: the one list `todo list` prints, in the order the repo works its epics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class Queue:
    """The ordered names of the epics the repo works, first to last."""

    name: str
    epics: tuple[str, ...] = ()

    source: ClassVar[tuple[str, ...]] = ("ostler/ostler/todo.py::list_epics", "ostler/ostler/todo.py::_write")


@dataclass(frozen=True)
class MintedEpic:
    """An epic a command created in this world. Its folder is named by an id the tool minted, which the book cannot
    know, so the model keeps the epic by its slug and the watch never lists its folder."""

    slug: str
    title: str = ""

    source: ClassVar[tuple[str, ...]] = ("ostler/ostler/crud.py::create_epic",)


@dataclass(frozen=True)
class MintedStory:
    """A story a command created in this world, kept by its epic's folder and its slug for the same reason."""

    key: str
    epic: str
    slug: str

    source: ClassVar[tuple[str, ...]] = ("ostler/ostler/crud.py::create_story",)
