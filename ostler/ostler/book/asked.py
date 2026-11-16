"""The data a list is filled from, asked of a backend through its book. The run sends the backend's own call as the
person taking the step and derives the list from the answer, so a phone, which sees no request, can state its lists
too."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book.errors import BookError
from ostler.book.http import Endpoint


@dataclass(frozen=True)
class Asked:
    """The answer of `call`, an endpoint class of another book, asked as the person taking the step."""

    call: type[Endpoint]

    @property
    def book(self) -> str:
        return ".".join(self.call.__module__.split(".")[:2])

    @property
    def text(self) -> str:
        return f"{self.call.__name__} of {self.book}"


@dataclass(frozen=True)
class Unasked:
    """Why the answer could not be had."""

    why: str


def asked(call: type[Endpoint]) -> Asked:
    if not (isinstance(call, type) and issubclass(call, Endpoint)):
        raise BookError(f"asked names an endpoint class of another book, as asked(ListTodos): it got {call!r}")
    return Asked(call)
