"""A todo as a client sends it. `todo` is the base factory; every other function
is a variant that fills one thing in and passes the rest through, so a journey
composes the fixture it needs in one line and never writes an id: the service
assigns it when the todo is added, and the fixture learns it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from ostler.book import Fixture

TITLE_MAX = 120


@dataclass(eq=False)
class Todo(Fixture):
    title: str | None = None
    description: str | None = None
    due_on: date | str | None = None
    assignee: str | None = None
    id: str | None = None

    def __str__(self) -> str:
        return self.title if self.title and self.title.strip() else "(untitled)"


def todo(title: str = "Water the plants", **fields: Any) -> Todo:
    return Todo(title=title, **fields)


def scheduled(today: date, days: int = 1, **fields: Any) -> Todo:
    return todo(due_on=today + timedelta(days=days), **fields)


def past_due(today: date, days: int = 1, **fields: Any) -> Todo:
    return todo(due_on=today - timedelta(days=days), **fields)


def assigned(who: str, **fields: Any) -> Todo:
    return todo(assignee=who, **fields)


def described(text: str, **fields: Any) -> Todo:
    return todo(description=text, **fields)


def blank_title(**fields: Any) -> Todo:
    return todo(title="   ", **fields)


def too_long_title(**fields: Any) -> Todo:
    return todo(title="x" * (TITLE_MAX + 1), **fields)


def stranger(**fields: Any) -> Todo:
    """A todo nobody added: an id the service never issued."""
    return todo(title="Something nobody added", **fields).set(id=str(uuid4()))
