"""Who calls. An `Actor` is a person the domain knows by a handle; a book
subclasses it to add what the domain knows of one (roles, a quota). `SOLE` is
the caller of a book with one user. An actor is a standing account by default:
saddlebag holds it, it exists in every environment, and every cell, run and
coworker shares it. `fresh` says why an actor needs an account no earlier cell
touched; an environment that cannot provision one skips the cells that need it."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Actor:
    handle: str
    fresh: str = field(default="", kw_only=True)

    @property
    def identity(self) -> str:
        return self.handle

    def __str__(self) -> str:
        return self.handle


SOLE = Actor("user")
KEEP = object()
