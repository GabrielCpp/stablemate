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
