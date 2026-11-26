"""What a service hands ostler: how to make a fresh model, the one surface the
service exposes, its journeys, its stack, what it declares (endpoints, or
screens and the interactions on them), the lifecycle matrices it answers for, and the words a command line
may use to name a request."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Generic, Mapping, TypeVar

from ostler.book.arrange import Arrange
from ostler.book.boundary import Person
from ostler.book.cast import SOLE, Actor
from ostler.book.domain import App, Documentation
from ostler.book.environment import OSTLER, Environment
from ostler.book.errors import BookError
from ostler.book.event import Event
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
from ostler.qa.addresses import LEASE_ENV

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
    events: tuple[type[Event], ...] = ()
    app: App | None = None
    documentation: Documentation | None = None
    records: tuple[type, ...] = ()
    environments: dict[str, Environment] = field(default_factory=dict)
    default_environment: str = ""
    languages: tuple[str, ...] = ()
    person: Person | None = None

    def __post_init__(self) -> None:
        self.declared()

    def declared(self) -> None:
        if self.app is not None and self.documentation is not None:
            raise BookError(f"{self.name} declares both app and documentation: a book describes code in the repository or a system outside it, not both")

    @property
    def language(self) -> str:
        """The first language the service declares, which a journey plays in unless it names another."""
        if not self.languages:
            raise BookError(f"{self.name} declares no languages: give Service languages=(...), the first being the one a journey plays in")
        return self.languages[0]

    def environment(self, name: str | None = None) -> Environment:
        """The environment *name* names. Unnamed, a process under a stack lease plays the one environment ostler serves, and any other plays the default."""
        chosen = name or self._leased_environment() or self.default_environment
        if chosen not in self.environments:
            raise BookError(f"{self.name} has no environment {chosen!r}; the environments are " + ", ".join(self.environments))
        return self.environments[chosen]

    def _leased_environment(self) -> str:
        if not os.environ.get(LEASE_ENV, ""):
            return ""
        served = [key for key, environment in self.environments.items() if any(url.startswith(OSTLER) for url in environment.hosts.values())]
        return served[0] if len(served) == 1 else ""
