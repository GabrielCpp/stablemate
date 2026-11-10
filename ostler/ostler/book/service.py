"""What a service hands ostler: how to make a fresh model, the one surface the
service exposes, its journeys, its stack, what it declares (endpoints, or
screens and the interactions on them), the lifecycle matrices it answers for, and the words a command line
may use to name a request."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Generic, Mapping, TypeVar

from ostler.book.arrange import Arrange
from ostler.book.cast import SOLE, Actor
from ostler.book.domain import App
from ostler.book.environment import Environment
from ostler.book.errors import BookError
from ostler.book.http import Endpoint
from ostler.book.inputs import Diverges
from ostler.book.journey import Journey
from ostler.book.model import Model
from ostler.book.outcome import Refusals
from ostler.book.screen import Interaction, Screen
from ostler.book.stack import Stack
from ostler.book.state import Axes
from ostler.book.surface import Surface
from ostler.book.witness import Unseen

S = TypeVar("S", bound=Model)


@dataclass
class Service(Generic[S]):
    name: str
    new_model: Callable[[date], S]
    surface: Callable[[Environment], Surface]
    journeys: tuple[type[Journey], ...]
    stack: Callable[[str], Stack]
    endpoints: tuple[type[Endpoint], ...] = ()
    screens: tuple[type[Screen], ...] = ()
    interactions: tuple[type[Interaction[Any]], ...] = ()
    matrices: tuple[Axes[S], ...] = ()
    words: Mapping[str, object] = field(default_factory=dict)
    cast: tuple[Actor, ...] = (SOLE,)
    unseen: tuple[Unseen, ...] = ()
    health: tuple[type[Journey], ...] = ()
    watch: tuple[Endpoint, ...] = ()
    refusals: Refusals = Refusals()
    diverges: tuple[Diverges, ...] = ()
    outside: tuple[type[Arrange[Any]], ...] = ()
    app: App | None = None
    records: tuple[type, ...] = ()
    environments: dict[str, Environment] = field(default_factory=dict)
    default_environment: str = ""

    def environment(self, name: str | None = None) -> Environment:
        chosen = name or self.default_environment
        if chosen not in self.environments:
            raise BookError(f"{self.name} has no environment {chosen!r}; the environments are " + ", ".join(self.environments))
        return self.environments[chosen]
