from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, cast
from uuid import uuid4

from ostler.book.errors import BookError


class Shape:
    def check(self, value: object, where: str = "body") -> list[str]:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class Str(Shape):
    format: str | None = None
    max_len: int | None = None
    classes: Mapping[str, str] = field(default_factory=dict, compare=False, hash=False)

    def check(self, value: object, where: str = "body") -> list[str]:
        if not isinstance(value, str):
            return [f"{where}: expected a string, got {type(value).__name__}"]
        if self.format == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                return [f"{where}: {value!r} is not a YYYY-MM-DD date"]
        if self.format == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return [f"{where}: {value!r} is not an RFC 3339 date-time"]
        form = FORMS.get(self.format or "")
        if form is not None and not form.pattern.match(value):
            return [f"{where}: {value!r} is not {form.meaning}"]
        if self.max_len is not None and len(value) > self.max_len:
            return [f"{where}: longer than {self.max_len}"]
        return []

    def fresh(self) -> str:
        """An identifier of this wire shape that names nothing."""
        form = FORMS.get(self.format or "")
        return form.fresh() if form is not None else str(uuid4())

    def near_misses(self) -> dict[str, str]:
        form = FORMS.get(self.format or "")
        if form is None:
            return {}
        value = form.fresh()
        out = {"one short": value[:-1], "one long": value + value[-1], "foreign character": value[:-1] + form.foreign}
        if form.unit > 1:
            out |= {"one unit short": value[:-form.unit], "one unit long": value + value[-form.unit:]}
        return out

    def describe(self) -> str:
        bits = ["string"]
        if self.format:
            bits.append(f"({self.format})")
        if self.max_len is not None:
            bits.append(f"≤ {self.max_len}")
        if self.classes:
            bits.append("classes: " + ", ".join(f"{k} ({v!r})" for k, v in self.classes.items()))
        return " ".join(bits)


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@dataclass(frozen=True)
class Form:
    pattern: re.Pattern[str]
    meaning: str
    fresh: Callable[[], str]
    foreign: str
    unit: int = 1


def _ulid() -> str:
    value = int.from_bytes(uuid4().bytes, "big") >> 2
    return "".join(_CROCKFORD[(value >> (5 * n)) & 31] for n in range(25, -1, -1))


FORMS: dict[str, Form] = {
    "hex32": Form(re.compile(r"^[0-9a-fA-F]{32}$"), "32 hexadecimal characters", lambda: uuid4().hex, "g", unit=2),
    "uuid": Form(re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"), "a UUID",
                 lambda: str(uuid4()), "g"),
    "ulid": Form(re.compile(r"^[0-7][0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{25}$"), "a ULID", _ulid, "U"),
}


@dataclass(frozen=True)
class Id(Shape):
    """The identifier of one record of the model. `kind` is the record class
    the model keeps, `of` the shape the id has on the wire. A model id of one
    kind is refused where another kind is typed. With `strangers` set, a value
    the book never issued is read back as written, and the text says why. With
    `minted` set, the book supplies the value and the client sends a unique one
    for it, and the text says why it must be unique in the environment."""

    kind: type
    of: Shape = Str(format="uuid")
    strangers: str = ""
    minted: str = ""

    def __post_init__(self) -> None:
        if self.strangers and self.minted:
            raise BookError(f"Id of {self.kind.__name__}: strangers and minted are both set; pick who makes the value")

    def check(self, value: object, where: str = "body") -> list[str]:
        return self.of.check(value, where)

    def describe(self) -> str:
        return f"id of {self.kind.__name__} ({self.of.describe()})"


@dataclass(frozen=True)
class Token(Shape):
    """A page token of the list `name` pages. The model keeps its own token and the app issues another: an answer is
    compared by whether a token is there, and the tool learns the pair, so a request carrying the model's token sends
    the app's. Two fields of one name are one token space."""

    name: str

    def check(self, value: object, where: str = "body") -> list[str]:
        return Str().check(value, where)

    def describe(self) -> str:
        return f"page token of {self.name}"


@dataclass(frozen=True)
class Enum(Shape):
    values: tuple[str, ...]

    def check(self, value: object, where: str = "body") -> list[str]:
        if value not in self.values:
            return [f"{where}: {value!r} is not one of {list(self.values)}"]
        return []

    def describe(self) -> str:
        return " | ".join(repr(v) for v in self.values)


@dataclass(frozen=True)
class Bool(Shape):
    def check(self, value: object, where: str = "body") -> list[str]:
        return [] if isinstance(value, bool) else [f"{where}: expected a boolean"]

    def describe(self) -> str:
        return "boolean"


@dataclass(frozen=True)
class Int(Shape):
    def check(self, value: object, where: str = "body") -> list[str]:
        return [] if isinstance(value, int) and not isinstance(value, bool) else [f"{where}: expected an integer"]

    def describe(self) -> str:
        return "integer"


@dataclass(frozen=True)
class Num(Shape):
    """A JSON number, never a boolean. With `text` a decimal written as a
    string. `places` is the most decimals allowed."""

    places: int | None = None
    text: bool = False
    min: float | None = None
    max: float | None = None

    def check(self, value: object, where: str = "body") -> list[str]:
        if self.text:
            if not isinstance(value, str):
                return [f"{where}: expected a decimal written as a string, got {type(value).__name__}"]
            raw: object = value
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return [f"{where}: expected a number, got {type(value).__name__}"]
            raw = repr(value)
        try:
            number = Decimal(str(raw))
        except InvalidOperation:
            return [f"{where}: {value!r} is not a decimal"]
        if not number.is_finite():
            return [f"{where}: {value!r} is not a finite number"]
        out: list[str] = []
        if self.places is not None and -cast(int, number.as_tuple().exponent) > self.places:
            out.append(f"{where}: more than {self.places} decimals")
        if self.min is not None and number < Decimal(str(self.min)):
            out.append(f"{where}: below {self.min}")
        if self.max is not None and number > Decimal(str(self.max)):
            out.append(f"{where}: above {self.max}")
        return out

    def describe(self) -> str:
        bits = ["decimal string" if self.text else "number"]
        if self.places is not None:
            bits.append(f"≤ {self.places} decimals")
        if self.min is not None:
            bits.append(f"≥ {self.min}")
        if self.max is not None:
            bits.append(f"≤ {self.max}")
        return " ".join(bits)


@dataclass(frozen=True)
class Map(Shape):
    """An object with any string keys, every value of one shape."""

    of: Shape

    def check(self, value: object, where: str = "body") -> list[str]:
        if not isinstance(value, dict):
            return [f"{where}: expected an object, got {type(value).__name__}"]
        out: list[str] = []
        for key, item in value.items():
            if not isinstance(key, str):
                out.append(f"{where}: key {key!r} is not a string")
            out += self.of.check(item, f"{where}[{key!r}]")
        return out

    def describe(self) -> str:
        return f"{{string: {self.of.describe()}}}"


@dataclass(frozen=True)
class Bytes(Shape):
    """A body that is not JSON: the bytes the service sent, which must start
    with `starts`."""

    starts: bytes = b""

    def check(self, value: object, where: str = "body") -> list[str]:
        if not isinstance(value, bytes):
            return [f"{where}: expected bytes, got {type(value).__name__}"]
        if not value.startswith(self.starts):
            return [f"{where}: does not start with {self.starts!r}"]
        return []

    def describe(self) -> str:
        return f"bytes starting {self.starts!r}" if self.starts else "bytes"


@dataclass(frozen=True)
class Itself(Shape):
    """A field that holds the enclosing object of this name, so a tree is one object and not one per level. The object
    replaces the placeholder when it is built; one that names no enclosing object refuses to check."""

    name: str

    def refusal(self) -> str:
        return f"Itself({self.name!r}) names no enclosing object {self.name!r}"

    def check(self, value: object, where: str = "body") -> list[str]:
        raise BookError(self.refusal())

    def describe(self) -> str:
        raise BookError(self.refusal())
