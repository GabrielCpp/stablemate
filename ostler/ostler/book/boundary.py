"""What a book says about a record its service does not own: which record and which of its fields it reads,
which named state a journey starts from, and how an answer derives from the owner's answer. The owner's book
makes the record and the owner's app answers about it; the book here only names them."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from ostler.book.errors import BookError
from ostler.book.status import Status


@dataclass(frozen=True)
class Foreign:
    """A record `owner`, the module name of its book, stores. `reads` lists the fields of the record this
    service reads."""

    record: type
    owner: str
    reads: tuple[str, ...]

    def __post_init__(self) -> None:
        held = {f.name for f in dataclasses.fields(self.record)} if dataclasses.is_dataclass(self.record) else set()
        lacking = [name for name in self.reads if name not in held and not hasattr(self.record, name)]
        if lacking:
            raise BookError(f"Foreign {self.record.__name__} reads {', '.join(lacking)}, which the record does not have")


class Needs:
    """A journey given: a record of `foreign` in the state `state`, a scene of one of the owner's matrices.
    The owner's book arranges it. Once it is, `id` is the id the owner's app issued and `record` the owner's
    model entity."""

    def __init__(self, foreign: Foreign, state: str):
        self.foreign = foreign
        self.state = state
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
        return f"needs {self.foreign.record.__name__} of {self.foreign.owner} in {self.state}"


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
