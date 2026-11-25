from __future__ import annotations

import json
from dataclasses import dataclass, is_dataclass
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Mapping, cast

from ostler.book import tree
from ostler.book.entries import says
from ostler.book.errors import BookError
from ostler.book.http_shapes import FORMS, Id, Num, Shape, Str
from ostler.book.model import attribute
from ostler.book.status import Status


@dataclass(frozen=True)
class Field:
    shape: Shape
    required: bool = True
    nullable: bool = False
    does: str = ""
    reads: str | None = None
    opaque: str = ""
    ignores: tuple[str, ...] = ()
    why: str = ""

    def __post_init__(self) -> None:
        unknown = [d for d in self.ignores if d not in DIMENSIONS]
        if unknown:
            raise BookError(f"Field ignores {unknown}: the dimensions are {list(DIMENSIONS)}")
        if self.ignores and not self.why.strip():
            raise BookError(f"Field ignores {list(self.ignores)}: say why the product is indifferent to it")

    def describe(self) -> str:
        bits = [self.shape.describe()]
        if self.nullable:
            bits.append("| null")
        if self.required:
            bits.append("(required)")
        if self.does:
            bits.append("— " + self.does)
        if self.reads:
            bits.append(f"(read from the model's {self.reads})")
        if self.opaque:
            compared = "not compared" if self.required and not self.nullable else "only whether it is set is compared"
            bits.append(f"({compared}: {self.opaque})")
        if self.ignores:
            bits.append(f"(indifferent to {', '.join(self.ignores)}: {self.why})")
        return " ".join(bits)


class Object(Shape):
    """A JSON object with declared fields. `pack` turns a fixture into the body
    to send: an object contributes each declared attribute it has, a None being
    left out; a dict is sent as written, so a null in it reaches the server."""

    def __init__(self, name: str = "", /, **fields: Field):
        self.name = name
        self.fields = fields
        self.one_ofs: tuple[tuple[str, ...], ...] = ()
        self.togethers: tuple[tuple[str, ...], ...] = ()
        if name:
            tree.bind(self)

    def one_of(self, *names: str) -> Object:
        return self._related(names, one_of=True)

    def together(self, *names: str) -> Object:
        return self._related(names, one_of=False)

    def _related(self, names: tuple[str, ...], *, one_of: bool) -> Object:
        unknown = [n for n in names if n not in self.fields]
        if len(names) < 2 or unknown:
            raise BookError(f"{self.name or 'body'}: a relation names two declared fields or more, not {list(names)}")
        out = Object(self.name, **self.fields)
        out.one_ofs = (*self.one_ofs, names) if one_of else self.one_ofs
        out.togethers = self.togethers if one_of else (*self.togethers, names)
        return tree.repoint(out, self)

    def check(self, value: object, where: str = "body") -> list[str]:
        if not isinstance(value, dict):
            return [f"{where}: expected an object, got {type(value).__name__}"]
        out: list[str] = []
        sent = {k for k, v in cast(Mapping[str, object], value).items() if v is not None}
        for names in self.one_ofs:
            if len(sent & set(names)) != 1:
                out.append(f"{where}: exactly one of {', '.join(names)}")
        for names in self.togethers:
            if 0 < len(sent & set(names)) < len(names):
                out.append(f"{where}: {', '.join(names)} come together or not at all")
        for key in value:
            if key not in self.fields:
                out.append(f"{where}.{key}: not declared")
        for key, spec in self.fields.items():
            if key not in value:
                if spec.required:
                    out.append(f"{where}.{key}: missing")
                continue
            got = cast(Mapping[str, object], value)[key]
            if got is None:
                if not spec.nullable:
                    out.append(f"{where}.{key}: null where not nullable")
                continue
            out += spec.shape.check(got, f"{where}.{key}")
        return out

    def pack(self, source: object) -> dict[str, Any]:
        if isinstance(source, Mapping):
            given = cast(Mapping[str, object], source)
            unknown = [k for k in given if k not in self.fields]
            if unknown:
                raise BookError(f"{self.name or 'body'} does not declare {unknown}")
            return {k: _wire(v, self.fields[k].shape) for k, v in given.items()}
        out: dict[str, Any] = {}
        for key, spec in self.fields.items():
            value = getattr(source, attribute(key), None)
            if value is not None:
                out[key] = _wire(value, spec.shape)
        return out

    def describe(self) -> str:
        return self.name or "object"

    def describe_fields(self, indent: str = "    ") -> str:
        width = max((len(k) for k in self.fields), default=0)
        return "\n".join(f"{indent}{k.ljust(width)}  {f.describe()}" for k, f in self.fields.items())


@dataclass(frozen=True)
class List(Shape):
    of: Shape
    unordered: str = ""
    entries: tuple[Callable[[list[Any]], list[str]], ...] = ()

    def __post_init__(self) -> None:
        if callable(self.entries):
            raise BookError("entries takes a tuple of rules, not one rule: write entries=(has(\"id\"),)")
        for rule in self.entries:
            if not says(rule):
                raise BookError(f"the entries rule {getattr(rule, '__name__', 'rule')} has no docstring: "
                                "its first line says what the entries hold, and search and explain show it")

    def check(self, value: object, where: str = "body") -> list[str]:
        if not isinstance(value, list):
            return [f"{where}: expected a list"]
        out: list[str] = []
        for n, item in enumerate(value):
            out += self.of.check(item, f"{where}[{n}]")
        return out

    def pack(self, source: object) -> list[Any]:
        items = cast("Iterable[object]", source)
        pack = getattr(self.of, "pack", None)
        return [pack(item) if pack is not None else _wire(item) for item in items]

    def describe(self) -> str:
        held = ", ".join(say for say in (f"any order: {self.unordered}" if self.unordered else "", *(says(rule) for rule in self.entries)) if say)
        return f"[{self.of.describe()}]" + (f" ({held})" if held else "")


DIMENSIONS = ("time of day", "offset", "surrounding spaces", "case", "trailing zeros", "order", "duplicate", "midnight")


def _written_day(current: object, today: date) -> str:
    if isinstance(current, str):
        try:
            return date.fromisoformat(current[:10]).isoformat()
        except ValueError:
            pass
    return (today + timedelta(days=2)).isoformat()


def _str_twins(shape: Str, current: object, today: date) -> list[tuple[str, object, object]]:
    if shape.format == "date-time":
        day = _written_day(current, today)
        return [("time of day", f"{day}T00:30:00+00:00", f"{day}T23:30:00+00:00"),
                ("offset", f"{day}T12:00:00+14:00", f"{day}T12:00:00-12:00")]
    if shape.format is not None and (shape.format in FORMS or shape.format == "date"):
        return []
    text = current.strip() if isinstance(current, str) and current.strip() else "sample"
    out: list[tuple[str, object, object]] = [("surrounding spaces", text, f"  {text}  ")]
    if text.lower() != text.upper():
        out.append(("case", text.lower(), text.upper()))
    return out


def _num_twins(shape: Num, current: object, today: date) -> list[tuple[str, object, object]]:
    if shape.text:
        plain = str(current) if isinstance(current, str) and "." not in current else "1"
        return [("trailing zeros", plain, f"{plain}.0"), ("trailing zeros", plain, f"{plain}.000")]
    whole = current if isinstance(current, int) and not isinstance(current, bool) else 1
    return [("trailing zeros", whole, float(whole))]


def _list_twins(shape: List, current: object, today: date) -> list[tuple[str, object, object]]:
    if not isinstance(current, list) or len(current) < 2:
        return []
    items = cast("list[object]", current)
    out: list[tuple[str, object, object]] = [("order", items, items[::-1])]
    if not isinstance(shape.of, Id):
        out.append(("duplicate", items, [*items, items[0]]))
    return out


TWINS: dict[type, Callable[..., list[tuple[str, object, object]]]] = {Str: _str_twins, Num: _num_twins, List: _list_twins}


def twins(shape: Shape, current: object, today: date) -> list[tuple[str, object, object]]:
    """Pairs of valid values that differ along one dimension the wire type
    carries: the dimension, the first value, the second. `current` is the value
    the call being varied holds, if any; the pair keeps the date it reads."""
    make = TWINS.get(type(shape))
    pairs = make(shape, current, today) if make is not None else []
    return [(d, a, b) for d, a, b in pairs if json.dumps(a, default=str) != json.dumps(b, default=str) and not shape.check(a) and not shape.check(b)]


def blind(shape: Shape | None, value: Any) -> Any:
    """An answer in the compared form with every id the shape types as an Id
    replaced by a placeholder, so two records made apart compare alike."""
    if isinstance(shape, Id):
        return None if value is None else "<id>"
    if isinstance(shape, List) and isinstance(value, (list, tuple)):
        items = [blind(shape.of, item) for item in cast("Iterable[Any]", value)]
        if shape.unordered:
            items.sort(key=str)
        return tuple(items)
    if isinstance(shape, Object) and isinstance(value, dict):
        return {k: blind(shape.fields[k].shape, v) if k in shape.fields else v for k, v in cast("dict[str, Any]", value).items()}
    return value


@dataclass(frozen=True)
class Bearer:
    """`Authorization: Bearer <token>`."""

    def header(self, credential: str) -> tuple[str, str]:
        return "Authorization", f"Bearer {credential}"

    def describe(self) -> str:
        return "bearer token"


@dataclass(frozen=True)
class ApiKey:
    name: str = "X-Api-Key"

    def header(self, credential: str) -> tuple[str, str]:
        return self.name, credential

    def describe(self) -> str:
        return f"{self.name} header"


Auth = Bearer | ApiKey


@dataclass(frozen=True)
class Answer:
    """One status the endpoint may give, the shape of the body that comes with
    it, and what it means. `creates` names the field whose value the fixture
    sent as body learns as its id."""

    status: Status
    body: Shape | None
    means: str
    creates: str | None = None
    why: str = ""


def _real(value: object) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def error_field(body: object) -> str:
    """The refusal message in an `error` field."""
    return str(cast("dict[str, object]", body).get("error", "")) if isinstance(body, dict) else str(body)


def problem(body: object) -> str:
    """The refusal message of an RFC 7807 problem: `detail`, else `title`."""
    if not isinstance(body, dict):
        return str(body)
    found = cast("dict[str, object]", body)
    return str(found.get("detail") or found.get("title") or "")


def _wire(value: object, shape: Shape | None = None) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(shape, Object) and is_dataclass(value) and not isinstance(value, type):
        return shape.pack(value)
    if isinstance(shape, List) and isinstance(value, (list, tuple)):
        return [_wire(item, shape.of) for item in cast("list[object]", value)]
    return value
