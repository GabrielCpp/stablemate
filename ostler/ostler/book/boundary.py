"""What a book says about a record its service does not own: which record and which of its fields it reads,
which named state a journey starts from, and how an answer derives from the owner's answer. The owner's book
makes the record and the owner's app answers about it; the book here only names them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping

from ostler.book.cast import Actor
from ostler.book.errors import BookError
from ostler.book.status import Status


class Word:
    """The name of a record whose owner has no book yet: it reads like a record class where only the name is asked."""

    def __init__(self, name: str):
        self.__name__ = name

    def __repr__(self) -> str:
        return f"Word({self.__name__!r})"


class View(Mapping[str, Any]):
    """The fields of the owner's view of one record that a screen reads, and only those: a read of any other fails."""

    def __init__(self, foreign: Foreign, shown: Mapping[str, Any]):
        self.foreign = foreign
        missing = [name for name in foreign.reads if name not in shown]
        if missing:
            raise BookError(f"the owner's view of {foreign.record.__name__} in {foreign.owner} has no {', '.join(missing)}: "
                            f"it has {', '.join(shown)}")
        self.shown = {name: shown[name] for name in foreign.reads}

    def __getitem__(self, name: str) -> Any:
        if name not in self.shown:
            raise BookError(f"{name!r} is not in the read set of {self.foreign.record.__name__} of {self.foreign.owner}: "
                            f"it reads {', '.join(self.shown)}")
        return self.shown[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.shown)

    def __len__(self) -> int:
        return len(self.shown)


@dataclass(frozen=True)
class Foreign:
    """A record `owner`, the module name of its book, stores. `reads` lists the fields of the owner's answers this
    service reads. `record` is the record class of the owner's book, or its name while that book is not written.
    A screen book gives `takes`: from its model, the id the owner's app issued and the `View` of the arranged record,
    it builds the transaction that puts the record in the screen's own model."""

    record: Any
    owner: str
    reads: tuple[str, ...]
    takes: Callable[[Any, str, View], Any] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.record, str):
            object.__setattr__(self, "record", Word(self.record))

    @property
    def named(self) -> bool:
        return isinstance(self.record, Word)


@dataclass(frozen=True)
class Person:
    """A cast member of the owner's book `owner`, whose account a page signs in with."""

    owner: str
    actor: Actor


class Needs:
    """A journey given: a record of `foreign` in the state `state`, a scene of one of the owner's matrices.
    `person` is the owner's cast member the record belongs to and the page plays as: the owner's scene is the
    one that person takes part in. The owner's book arranges it. Once it is, `id` is the id the owner's app
    issued and `record` the owner's model entity."""

    def __init__(self, foreign: Foreign, state: str, person: Actor | None = None):
        if foreign.named:
            raise BookError(f"{foreign.owner} has no book to arrange {foreign.record.__name__} in {state}: "
                            "name the record class of its book once it has one")
        self.foreign = foreign
        self.state = state
        self.person = person
        self.held: tuple[str, object] | None = None

    def arranged(self, ident: str, record: object) -> None:
        self.held = (ident, record)

    def forget(self) -> None:
        self.held = None

    def _held(self) -> tuple[str, object]:
        if self.held is None:
            raise BookError(f"{self} was not arranged before it was read: take it as a journey given")
        return self.held

    @property
    def id(self) -> str:
        return self._held()[0]

    @property
    def record(self) -> object:
        return self._held()[1]

    def __str__(self) -> str:
        return f"needs {self.foreign.record.__name__} of {self.foreign.owner} in {self.state}" + (f" for {self.person}" if self.person else "")


@dataclass(frozen=True)
class Passes:
    """On an endpoint that carries no action: `asks` builds the owner's call from the step, and `derived`
    turns the owner's answer body into the body this endpoint must answer. `refused` maps each status the
    owner refuses with to the status this endpoint answers with."""

    asks: Callable[[Any], Any]
    derived: Callable[[Any], Any]
    refused: Mapping[Any, Status] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (self.derived.__doc__ or "").strip():
            raise BookError(f"the derived function {getattr(self.derived, '__name__', 'derived')} has no docstring: "
                            "its first line says what the endpoint passes on, and search and explain show it")

    def says(self) -> str:
        return (self.derived.__doc__ or "").strip().splitlines()[0]


@dataclass(frozen=True)
class Reaches:
    """On an endpoint that carries no action: a call of this service arrives at the owner's call `call` builds
    from the step. The owner's book states what that call does; `refused` maps each status the owner refuses
    it with to the status this endpoint answers with."""

    call: Callable[[Any], Any]
    refused: Mapping[Any, Status] = field(default_factory=dict)
