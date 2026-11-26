from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from ostler.book.errors import BookError
from ostler.book.http_objects import Answer, error_field
from ostler.book.http_shapes import Id, Shape, Str, Token
from ostler.book.outcome import Refusal
from ostler.book.status import Status, redirected, refused


@dataclass(frozen=True)
class Reference:
    """A value only the service knows: a type id, a default sheet. A fixture
    field may hold one. The client registers what it stands for with `know`;
    `pack` puts that on the wire, and the model never reads it."""

    name: str

    def __str__(self) -> str:
        return f"<{self.name}>"


@dataclass
class Reply:
    """A redirect reads as a refusal whose message is where it sends the caller, so a rule names that place."""

    status: Status
    body: Any
    answer: Answer
    message_of: Callable[[object], str] = error_field
    whole: Any = None
    location: str = ""

    @property
    def refusal(self) -> Refusal | None:
        if redirected(self.status):
            return Refusal(self.location, self.status)
        if not refused(self.status):
            return None
        return Refusal(self.message_of(self.body), self.status)


class Identities:
    """The ids the app issued, by the kind of record they belong to: for each
    kind, the model's id of a record and the id the app gave it."""

    def __init__(self) -> None:
        self.by_kind: dict[type, dict[str, str]] = {}
        self.tokens: dict[str, dict[str, str]] = {}

    def learn(self, kind: type, model: str, real: str) -> None:
        self.by_kind.setdefault(kind, {})[model] = real

    def real(self, kind: type, model: str) -> str | None:
        return self.by_kind.get(kind, {}).get(model)

    def learn_token(self, name: str, model: str, real: str) -> None:
        self.tokens.setdefault(name, {})[model] = real

    def real_token(self, name: str, model: str) -> str | None:
        return self.tokens.get(name, {}).get(model)

    def model_of(self, kind: type, real: str) -> str | None:
        return next((m for m, r in self.by_kind.get(kind, {}).items() if r == real), None)

    def minted(self, kind: type, name: str, room: int | None = None) -> str:
        """The unique value this run sends for the name the book wrote, made on
        first use and kept. An empty name, or one of spaces alone, is sent as it
        is, so a blank stays a blank. The made value is the name, a dash and eight hex characters;
        where that would pass `room`, the bound the shape declares, the tail of
        the name gives way instead, so a value at a bound stays at it and one
        past it stays past it. A name held in another case gives the held
        value in that case."""
        if not name.strip():
            return name
        held = self.real(kind, name)
        if held is not None:
            return held
        for known, real in list(self.by_kind.get(kind, {}).items()):
            recased = real.upper() if name == known.upper() else real.lower() if name == known.lower() else None
            if recased is not None:
                self.learn(kind, name, recased)
                return recased
        tail = uuid4().hex[:8]
        fits = room is None or len(name) + len(tail) + 1 <= room
        made = f"{name}-{tail}" if fits or len(name) <= len(tail) + 1 else f"{name[:-len(tail) - 1]}-{tail}"
        self.learn(kind, name, made)
        return made

    def spoken(self, text: str) -> str:
        """A message as the model says it: an id the app issued, quoted whole,
        reads as the model's id of the same record."""
        for known in self.by_kind.values():
            for model, real in known.items():
                if model != real and real in text:
                    text = re.sub(rf"(?<![\w-]){re.escape(real)}(?![\w-])", lambda found: model, text)
        return text

    def kind_of(self, model: str) -> type | None:
        return next((k for k, known in self.by_kind.items() if known.get(model, model) != model), None)

    def clear(self) -> None:
        self.by_kind.clear()
        self.tokens.clear()


def unknown_value(shape: Shape) -> str:
    """A value of this shape's wire form that names nothing."""
    wire = shape.of if isinstance(shape, Id) else shape
    return wire.fresh() if isinstance(wire, Str) else str(uuid4())


def real_id(shape: Id, value: object, ids: Identities | None, where: str) -> str:
    """The id the app knows for the model id `value`. An id the book never
    issued, a stranger, goes through as written. A minted id is made unique on
    first use and the same real value goes out each time after."""
    text = str(value)
    if ids is None:
        return text
    if shape.minted:
        return ids.minted(shape.kind, text, shape.of.max_len if isinstance(shape.of, Str) else None)
    found = ids.real(shape.kind, text)
    if found is not None:
        return found
    other = ids.kind_of(text)
    if other is not None:
        raise BookError(f"{where}: {text} is the id of a {other.__name__}, sent where an id of {shape.kind.__name__} is typed")
    return text


def real_token(shape: Token, value: object, ids: Identities | None) -> str | None:
    """The token the app knows for the model token `value`: the one learned for this name, else the value as written.
    None or an empty value is no token and sends nothing."""
    if value is None or value == "":
        return None
    text = str(value)
    found = ids.real_token(shape.name, text) if ids is not None else None
    return text if found is None else found


def wired(shape: Shape | None, value: object, ids: Identities | None, where: str) -> object:
    """The value as the app is sent it: an id turned into the app's id of its kind, a page token into the app's token."""
    if isinstance(shape, Token):
        return real_token(shape, value, ids)
    if isinstance(shape, Id):
        return real_id(shape, value, ids, where)
    return value
