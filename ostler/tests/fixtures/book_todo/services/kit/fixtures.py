"""What a journey hands the kit app: the todo a user types and the owner they pick, which is the web book's fixture, and
the name picked on the assign page."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book import Fixture

from ..web.fixtures import Todo, todo


@dataclass(eq=False)
class Who(Fixture):
    name: str

    def __str__(self) -> str:
        return self.name


__all__ = ["Todo", "Who", "todo"]
