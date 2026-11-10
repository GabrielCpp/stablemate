"""One HTTP endpoint, declared once and called through the declaration.

A service writes one subclass per endpoint and gives it no method. The class
body is the whole contract: method, path, the credentials it accepts, the shape
of its path parameters, query and body, and every answer it may give with the
shape of that answer's body. `send` fills the path from the declaration, picks a
credential the client holds, serialises the call, and refuses to accept an
answer the declaration does not list or a body that does not fit the shape
declared for that status. That is the check an OpenAPI document promises and
never performs.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4
from dataclasses import dataclass, field, is_dataclass
from datetime import date, datetime
from typing import Any, Callable, ClassVar, Iterable, Mapping, cast

from ostler.book.cast import KEEP, SOLE, Actor
from ostler.book.domain import Action, Fixture, Heard, On
from ostler.book.errors import BookError, Unhealthy
from ostler.book.model import attribute
from ostler.book.outcome import Refusal, Refusals
from ostler.book.status import Code, Status, refused, succeeded

__all__ = ["BookError"]


class Undeclared(Exception):
    """The app answered with a status the endpoint does not declare."""

    def __init__(self, endpoint: type[Endpoint], status: Status, body: object):
        super().__init__(f"{endpoint.__name__} answered {status}, which it does not declare; body {body!r}")
        self.status = status


class OffShape(Exception):
    """The app's body does not fit the shape declared for that status."""

    def __init__(self, endpoint: type[Endpoint], status: Status, mismatches: list[str]):
        super().__init__(f"{endpoint.__name__} answered {status} with a body off its shape: " + "; ".join(mismatches))
        self.mismatches = mismatches


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
class Field:
    shape: Shape
    required: bool = True
    nullable: bool = False
    does: str = ""
    reads: str | None = None
    opaque: str = ""

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
        return out

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
        return f"[{self.of.describe()}]" + (f" (any order: {self.unordered})" if self.unordered else "")


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


def declared_paths(shape: Shape | None, prefix: str = "") -> list[str]:
    """Every field path a shape declares, going through lists as `lines[].quantity`."""
    if isinstance(shape, Object):
        out: list[str] = []
        for key, spec in shape.fields.items():
            path = f"{prefix}.{key}" if prefix else key
            out.append(path)
            out += declared_paths(spec.shape, path)
        return out
    if isinstance(shape, List):
        return declared_paths(shape.of, prefix + "[]")
    if isinstance(shape, Map):
        return declared_paths(shape.of, prefix + "{}")
    return []


def real_paths(shape: Shape | None, value: object, prefix: str = "", ids: Identities | None = None) -> set[str]:
    """The declared field paths at which this value holds something real. A list
    entry the comparison drops, one naming an id the book never issued, shows
    nothing: the run did not check it."""
    out: set[str] = set()
    if isinstance(shape, Object) and isinstance(value, dict):
        for key, spec in shape.fields.items():
            if _real(value.get(key)):
                path = f"{prefix}.{key}" if prefix else key
                out.add(path)
                out |= real_paths(spec.shape, cast(dict[str, Any], value)[key], path, ids)
    elif isinstance(shape, List) and isinstance(value, list):
        for item in value:
            if ids is not None and _unknown(canonical(shape.of, item, app=True, ids=ids, where=prefix + "[]")):
                continue
            out |= real_paths(shape.of, item, prefix + "[]", ids)
    elif isinstance(shape, Map) and isinstance(value, dict):
        for item in value.values():
            out |= real_paths(shape.of, item, prefix + "{}", ids)
    return out


class Witness:
    """What a client has seen the service do: for each endpoint the statuses it
    answered, and for each answer the field paths that held a real value. Real
    is not null, not an empty string, list or object."""

    def __init__(self) -> None:
        self.statuses: dict[type[Endpoint], set[Status]] = {}
        self._fields: dict[tuple[type[Endpoint], Status], set[str]] = {}
        self._pending: list[tuple[type[Endpoint], Answer, object, Identities | None]] = []

    def see(self, endpoint: type[Endpoint], answer: Answer, body: object, ids: Identities | None = None) -> None:
        self.statuses.setdefault(endpoint, set()).add(answer.status)
        self._pending.append((endpoint, answer, body, ids))

    def settle(self) -> None:
        for endpoint, answer, body, ids in self._pending:
            self._fields.setdefault((endpoint, answer.status), set()).update(real_paths(answer.body, body, "", ids))
        self._pending.clear()

    @property
    def fields(self) -> dict[tuple[type[Endpoint], Status], set[str]]:
        self.settle()
        return self._fields

    def merge(self, other: Witness) -> None:
        for endpoint, statuses in other.statuses.items():
            self.statuses.setdefault(endpoint, set()).update(statuses)
        for key, paths in other.fields.items():
            self.fields.setdefault(key, set()).update(paths)


def error_field(body: object) -> str:
    """The refusal message in an `error` field."""
    return str(cast("dict[str, object]", body).get("error", "")) if isinstance(body, dict) else str(body)


def problem(body: object) -> str:
    """The refusal message of an RFC 7807 problem: `detail`, else `title`."""
    if not isinstance(body, dict):
        return str(body)
    found = cast("dict[str, object]", body)
    return str(found.get("detail") or found.get("title") or "")


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
    status: Status
    body: Any
    answer: Answer
    message_of: Callable[[object], str] = error_field

    @property
    def refusal(self) -> Refusal | None:
        if not refused(self.status):
            return None
        return Refusal(self.message_of(self.body), self.status)


class Identities:
    """The ids the app issued, by the kind of record they belong to: for each
    kind, the model's id of a record and the id the app gave it."""

    def __init__(self) -> None:
        self.by_kind: dict[type, dict[str, str]] = {}

    def learn(self, kind: type, model: str, real: str) -> None:
        self.by_kind.setdefault(kind, {})[model] = real

    def real(self, kind: type, model: str) -> str | None:
        return self.by_kind.get(kind, {}).get(model)

    def model_of(self, kind: type, real: str) -> str | None:
        return next((m for m, r in self.by_kind.get(kind, {}).items() if r == real), None)

    def minted(self, kind: type, name: str, room: int | None = None) -> str:
        """The unique value this run sends for the name the book wrote, made on
        first use and kept. An empty name is sent as it is, so a blank stays a
        blank. The made value is the name, a dash and eight hex characters;
        where that would pass `room`, the bound the shape declares, the tail of
        the name gives way instead, so a value at a bound stays at it and one
        past it stays past it. A name held in another case gives the held
        value in that case."""
        if not name:
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


class Client:
    """Where the service listens and the credentials each caller holds, one per
    scheme. `credentials` are the sole caller's. `send` is the one way through."""

    def __init__(self, base: str, credentials: Mapping[Auth, str] | None = None, timeout: float = 10,
                 message_of: Callable[[object], str] = error_field, hosts: Mapping[str, str] | None = None):
        self.base = base.rstrip("/")
        self.message_of = message_of
        self.hosts = {name: address.rstrip("/") for name, address in (hosts or {}).items()}
        self.held: dict[tuple[Actor, Auth], str] = {(SOLE, auth): value for auth, value in (credentials or {}).items()}
        self.timeout = timeout
        self.ids = Identities()
        self.witness = Witness()
        self.known: dict[str, object] = {}
        self.resolved: dict[str, Any] = {}

    def know(self, name: str, value: object) -> None:
        """Say what the reference `name` stands for: a value, or a callable
        that returns it, called once on first use."""
        self.known[name] = value
        self.resolved.pop(name, None)

    def resolve(self, reference: Reference) -> Any:
        if reference.name not in self.resolved:
            if reference.name not in self.known:
                raise BookError(f"the client knows nothing called {reference.name!r}; register it with client.know")
            value = self.known[reference.name]
            self.resolved[reference.name] = cast(Callable[[], Any], value)() if callable(value) else value
        return self.resolved[reference.name]

    def hold(self, actor: Actor, auth: Auth, credential: str) -> None:
        """Keep the credential `actor` presents under `auth`."""
        self.held[(actor, auth)] = credential

    def forget(self) -> None:
        self.witness.settle()
        self.ids.clear()

    def address(self, host: str) -> str:
        if not host:
            return self.base
        if host not in self.hosts:
            raise BookError(f"the client knows no host called {host!r}")
        return self.hosts[host]

    def send(self, call: Endpoint) -> Reply:
        return call.send(self)

    def transport(self, method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[Status, bytes]:
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as reply:
                return reply.status, reply.read()
        except urllib.error.HTTPError as reply:
            return reply.code, reply.read()
        except (urllib.error.URLError, OSError) as down:
            raise Unhealthy(f"{method} {url} did not answer: {getattr(down, 'reason', down)}") from None


GATEWAY: tuple[Status, ...] = (502, 503, 504, Code.UNAVAILABLE)
_PARAM = re.compile(r"{(\w+)}")
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


class Endpoint:
    """Subclass per endpoint. The class body declares; an instance is one call."""

    method: ClassVar[str] = "GET"
    path: ClassVar[str] = "/"
    auth: ClassVar[tuple[Auth, ...]] = ()
    params: ClassVar[Object] = Object()
    query: ClassVar[Object | None] = None
    body: ClassVar[Object | List | Bytes | None] = None
    headers: ClassVar[Object | None] = None
    refusals: ClassVar[Refusals] = Refusals()
    host: ClassVar[str] = ""
    answers: ClassVar[tuple[Answer, ...]] = ()
    does: ClassVar[str] = ""
    carries: ClassVar[type[Action[Any, Any]] | None] = None
    source: ClassVar[tuple[str, ...]] = ()
    unauthenticated: ClassVar[Status] = 401
    typed_wire: ClassVar[bool] = False

    def __init_subclass__(cls, abstract: bool = False) -> None:
        if abstract:
            return
        name = cls.__name__
        if cls.method not in METHODS:
            raise BookError(f"{name}: method {cls.method!r} is not one of {METHODS}")
        in_path = set(_PARAM.findall(cls.path))
        declared = set(cls.params.fields)
        if in_path != declared:
            raise BookError(f"{name}: path names {sorted(in_path)} but params declare {sorted(declared)}")
        if cls.body is not None and cls.method in ("GET", "DELETE"):
            raise BookError(f"{name}: a {cls.method} carries no body")
        if not cls.answers:
            raise BookError(f"{name}: declares no answer")
        statuses = [a.status for a in cls.answers]
        if len(statuses) != len(set(statuses)):
            raise BookError(f"{name}: a status is declared twice")
        if cls.auth and cls.unauthenticated not in statuses:
            raise BookError(f"{name}: accepts credentials but never answers {cls.unauthenticated}")

    @classmethod
    def route(cls) -> str:
        """The call as its protocol names it."""
        return f"{cls.method} {cls.path}"

    @classmethod
    def read(cls, answer: Answer, raw: bytes) -> object:
        """The body of an answer, named as the declared shape names it."""
        return raw if isinstance(answer.body, Bytes) else (json.loads(raw) if raw else None)

    def __init__(self, of: object = None, *, query: Mapping[str, object] | Fixture | None = None,
                 body: object = None, makes: object = None, by: Actor | None | object = KEEP,
                 auth: Auth | object = KEEP, headers: Mapping[str, object] | None = None):
        cls = type(self)
        if isinstance(of, On):
            if cls.body is None and makes is None and body is None:
                of, makes = of.target, of.body
            elif body is None and makes is None:
                of, body = of.target, of.body
        if of is not None and not cls.params.fields and cls.body is None:
            raise BookError(f"{cls.__name__} takes no path parameter")
        if makes is not None and cls.body is not None:
            raise BookError(f"{cls.__name__} sends a body, so it makes nothing apart from it")
        if makes is not None and not any(a.creates for a in cls.answers):
            raise BookError(f"{cls.__name__} declares no answer that creates")
        on = body is not None and of is not None and bool(cls.params.fields)
        if cls.body is not None and body is None and of is not None and not isinstance(of, tuple):
            body = of
        if of is not None and not cls.params.fields:
            of = None
        if of is None and cls.params.fields:
            raise BookError(f"{cls.__name__} needs {list(cls.params.fields)}")
        if query and cls.query is None:
            raise BookError(f"{cls.__name__} declares no query")
        if query is None and cls.query is not None and isinstance(of, Fixture):
            query = {k: v for k, v in vars(of).items() if k in cls.query.fields and v is not None} or None
        if headers and cls.headers is None:
            raise BookError(f"{cls.__name__} declares no headers")
        if body is not None and cls.body is None:
            raise BookError(f"{cls.__name__} declares no body")
        if body is None and cls.body is not None:
            raise BookError(f"{cls.__name__} needs a body")
        self.of = of
        self.on = On(of, body) if on else None
        self.makes = makes
        self.query_given = query
        self.query_values = _as_values(query)
        self.body_value = body
        self.taken: object | None = None
        self.header_values: dict[str, object] = dict(headers or {})
        self.reply: Reply | None = None
        self.by: Actor | None = SOLE if by is KEEP else cast("Actor | None", by)
        self.auth_used: Auth | None = (cls.auth[0] if cls.auth else None) if auth is KEEP else cast("Auth | None", auth)
        if self.auth_used is not None and self.auth_used not in cls.auth:
            raise BookError(f"{cls.__name__} does not accept {self.auth_used.describe()}")

    def input(self) -> object:
        """What the carried model action receives: the body when one is sent,
        else the thing the path points at, else the query. An endpoint that
        declares headers hands them along with it, as a `Heard`."""
        given = self.given()
        if type(self).headers is None:
            return given
        return Heard(given, tuple(self.header_values.items()))

    def given(self) -> object:
        cls = type(self)
        if self.on is not None:
            if isinstance(self.on.body, Mapping):
                named = {k: v for k, v in self.path_values(strict=False).items() if not v.startswith("{")}
                return {**named, **cast(Mapping[str, object], self.on.body)}
            return self.on
        if self.makes is not None:
            return On(self.of, self.makes) if self.of is not None else self.makes
        if cls.body is not None:
            return self._taken()
        if cls.params.fields:
            return self.of
        return self.query_given if isinstance(self.query_given, Fixture) else self.query_values

    def _taken(self) -> object:
        action = type(self).carries
        if self.taken is None and isinstance(self.body_value, Mapping) and action is not None and action.accept is not None:
            try:
                self.taken = action.listen(self.body_value)
            except BookError:
                return self.body_value
        return self.taken if self.taken is not None else self.body_value

    def varied(self, *, of: object = KEEP, body: object = KEEP, query: object = KEEP, headers: object = KEEP) -> Endpoint:
        """The same call with one input replaced. A body that was the very thing
        the path points at moves with it."""
        cls = type(self)
        aliased = self.body_value is not None and self.body_value is self.of
        new_of = self.of if of is KEEP else of
        new_body = self.body_value if body is KEEP else body
        if aliased and body is KEEP:
            new_body = new_of
        if cls.params.fields and cls.body is not None:
            first = new_of if new_body is new_of else On(new_of, new_body)
        elif cls.params.fields:
            first = new_of
        else:
            first = new_body if cls.body is not None else None
        return cls(first, query=self.query_given if query is KEEP else cast("Mapping[str, object] | None", query),
                   makes=self.makes, by=self.by, auth=self.auth_used,
                   headers=self.header_values if headers is KEEP else cast("Mapping[str, object] | None", headers))

    def path_values(self, strict: bool = True, ids: Identities | None = None,
                    know: Callable[[Reference], Any] | None = None) -> dict[str, str]:
        cls = type(self)
        if not cls.params.fields:
            return {}
        names = _PARAM.findall(cls.path)
        if isinstance(self.of, tuple):
            if len(self.of) != len(names):
                raise BookError(f"{cls.__name__}: {len(self.of)} values for the parameters {names}")
            values = dict(zip(names, self.of))
        elif isinstance(self.of, Mapping):
            values = dict(self.of)
        else:
            values = {name: self.of for name in names}
        out: dict[str, str] = {}
        for name in names:
            value = values[name]
            value = getattr(value, name, value)
            if isinstance(value, Reference) and know is not None:
                value = know(value)
            if value is None and strict:
                raise BookError(f"{cls.__name__}: {name} is not known yet; was the fixture created?")
            shape = cls.params.fields[name].shape
            if value is not None and isinstance(shape, Id):
                value = real_id(shape, value, ids, f"{cls.__name__} path {name}")
            out[name] = "{" + name + "}" if value is None else str(value)
        return out

    def url(self, base: str, ids: Identities | None = None,
            know: Callable[[Reference], Any] | None = None) -> str:
        cls = type(self)
        path = cls.path
        for name, value in self.path_values(ids=ids, know=know).items():
            path = path.replace("{" + name + "}", urllib.parse.quote(value, safe=""))
        if self.query_values:
            if cls.query is not None:
                cls.query.pack(self.query_values)
            pairs = [(k, _wire(self._query_value(k, v, ids, know))) for k, v in self.query_values.items() if v is not None]
            path += "?" + urllib.parse.urlencode(pairs)
        return base + path

    def id_inputs(self) -> list[tuple[str, Id, str]]:
        """Every model id this call sends in a place typed Id: where, the shape, the id."""
        cls = type(self)
        out: list[tuple[str, Id, str]] = []
        for name, value in self.path_values(strict=False).items():
            shape = cls.params.fields[name].shape
            if isinstance(shape, Id) and not value.startswith("{"):
                out.append((f"{cls.__name__} path {name}", shape, value))
        for name, value in self.query_values.items():
            spec = cls.query.fields.get(name) if cls.query is not None else None
            if spec is not None and isinstance(spec.shape, Id) and value is not None and not isinstance(value, Reference):
                out.append((f"{cls.__name__} query {name}", spec.shape, str(value)))
        if isinstance(cls.body, (Object, List)):
            _id_values(cls.body, cls.body.pack(self.body_value), f"{cls.__name__} body", out)
        return out

    def id_faults(self, model: Any) -> list[str]:
        """The model ids this call sends where another kind of record is typed."""
        faults: list[str] = []
        names = model.collections() if hasattr(model, "collections") else {}
        for where, shape, value in self.id_inputs():
            holders = [c.of for c in (getattr(model, n) for n in names) if value in c]
            if holders and shape.kind not in holders:
                faults.append(f"{where}: {value} is the id of a {holders[0].__name__}, typed as an id of {shape.kind.__name__}")
        return faults

    def _query_value(self, name: str, value: object, ids: Identities | None,
                     know: Callable[[Reference], Any] | None) -> object:
        cls = type(self)
        value = _known(value, know)
        spec = cls.query.fields.get(name) if cls.query is not None else None
        if spec is not None and isinstance(spec.shape, Id):
            return real_id(spec.shape, value, ids, f"{cls.__name__} query {name}")
        return value

    def payload(self, ids: Identities | None = None, know: Callable[[Reference], Any] | None = None) -> Any:
        cls = type(self)
        if cls.body is None:
            return None
        if isinstance(cls.body, Bytes):
            return self.body_value
        return _prepared(cls.body, cast("Object | List", cls.body).pack(self.body_value), ids, know,
                         f"{cls.__name__} body")

    def send(self, client: Client) -> Reply:
        cls = type(self)
        headers = {"Content-Type": "application/json"}
        for name, value in self.header_values.items():
            if value is not None:
                headers[name] = str(_wire(value))
        if self.auth_used is not None and self.by is not None:
            credential = client.held.get((self.by, self.auth_used))
            if credential is None:
                raise BookError(f"the client holds no {self.auth_used.describe()} for {self.by}")
            name, value = self.auth_used.header(credential)
            headers[name] = value
        payload = self.payload(client.ids, client.resolve)
        if isinstance(payload, bytes):
            data, headers["Content-Type"] = payload, "application/octet-stream"
        else:
            data = None if payload is None else json.dumps(payload).encode()
        status, raw = client.transport(cls.method, self.url(client.address(cls.host), client.ids, client.resolve), headers, data)
        answer = next((a for a in cls.answers if a.status == status), None)
        if answer is None and status in GATEWAY:
            raise Unhealthy(f"{cls.route()} answered {status}: the service is not there to answer")
        if answer is None:
            raise Undeclared(cls, status, _loose(raw))
        parsed = cls.read(answer, raw)
        if answer.body is None:
            if parsed is not None:
                raise OffShape(cls, status, ["a body where none is declared"])
        else:
            mismatches = answer.body.check(parsed)
            if mismatches:
                raise OffShape(cls, status, mismatches)
        learner = self.makes if self.makes is not None else self.taken if self.taken is not None else self.body_value
        if answer.creates and isinstance(parsed, Mapping) and learner is not None and not isinstance(learner, (Mapping, list, bytes)):
            issued = cast(Object, answer.body).fields[answer.creates].shape
            if not isinstance(issued, Id):
                raise BookError(f"{cls.__name__}: {answer.creates} is created by the answer but is not typed Id")
            known = getattr(learner, answer.creates, None)
            issued_id = cast(Mapping[str, Any], parsed)[answer.creates]
            if known is None:
                setattr(learner, answer.creates, issued_id)
                client.ids.learn(issued.kind, str(issued_id), str(issued_id))
            else:
                client.ids.learn(issued.kind, str(known), str(issued_id))
        client.witness.see(cls, answer, parsed, client.ids)
        self.reply = Reply(status, parsed, answer, lambda body: client.ids.spoken(client.message_of(body)))
        return self.reply

    def __str__(self) -> str:
        cls = type(self)
        bits = [cls.route()]
        if self.of is not None:
            bits.append(f"of {self.of}")
        if self.query_values:
            bits.append("?" + "&".join(f"{k}={_wire(v)}" for k, v in self.query_values.items() if v is not None))
        if cls.body is not None:
            bits.append(repr(self.payload()) if isinstance(cls.body, Bytes) else json.dumps(self.payload(), ensure_ascii=False, default=str))
        if self.by is None and cls.auth:
            bits.append("(by nobody)")
        elif self.by is not None and self.by is not SOLE:
            bits.append(f"(by {self.by})")
        if self.by is not None and self.auth_used is not None and self.auth_used is not cls.auth[0]:
            bits.append(f"(with {self.auth_used.describe()})")
        return " ".join(bits)

    def replay(self) -> str:
        """The call as an expression over the book's own words, to take it again."""
        parts = []
        target = self.of if type(self).params.fields else self.body_value
        if target is not None:
            parts.append(_expr(target))
        if self.query_given:
            parts.append("query=" + _expr(self.query_given))
        if self.body_value is not None and self.body_value is not target:
            parts.append("body=" + _expr(self.body_value))
        if self.by is None:
            parts.append("by=None")
        elif self.by is not SOLE:
            parts.append(f"by={self.by!r}")
        return f"{type(self).__name__}({', '.join(parts)})"

    @classmethod
    def success(cls) -> Answer | None:
        """The answer a model that accepts the call stands for: the first 2xx that has a body."""
        return next((a for a in cls.answers if succeeded(a.status) and a.body is not None), None)

    def view_faults(self, view: tuple[object, ...] | None) -> list[str]:
        """The compared fields of the answer the model's view cannot supply."""
        answer = type(self).success()
        if answer is None or not view:
            return []
        shape = answer.body.of if isinstance(answer.body, List) else answer.body
        if not isinstance(shape, Object):
            return []
        return [f"{type(self).__name__} {answer.status}: {name} is neither carried by the model's view nor opaque"
                for name, spec in shape.fields.items()
                if not spec.opaque and not hasattr(view[0], spec.reads or name)]

    @classmethod
    def describe(cls) -> str:
        lines = [cls.route(), f"  {cls.does}"]
        lines.append("  auth: " + (" or ".join(a.describe() for a in cls.auth) if cls.auth else "none"))
        if cls.params.fields:
            lines.append("  path:")
            lines.append(cls.params.describe_fields())
        if cls.query is not None:
            lines.append("  query:")
            lines.append(cls.query.describe_fields())
        if cls.headers is not None:
            lines.append("  headers:")
            lines.append(cls.headers.describe_fields())
        if cls.body is not None:
            lines.append(f"  body: {cls.body.describe()}")
            if isinstance(cls.body, Object) and not cls.body.name:
                lines.append(cls.body.describe_fields())
        for answer in cls.answers:
            shape = answer.body.describe() if answer.body is not None else "no body"
            for where, why in opaque_fields(answer.body):
                lines.append(f"    not compared at {answer.status} {where}: {why}")
            extra = f"; the fixture learns its {answer.creates}" if answer.creates else ""
            lines.append(f"  {answer.status} → {shape}: {answer.means}{extra}")
            if answer.why:
                lines.append(f"    why: {answer.why}")
        if cls.carries is not None:
            carried: type[Action[Any, Any]] = cls.carries
            lines.append(f"  carries: {carried.__name__}")
            for rule in carried.rules:
                lines.append(f"    refuses {rule.status} {rule.message!r}")
                if rule.why:
                    lines.append(f"      why: {rule.why}")
            for defect in carried.defects:
                lines.append(f"    known defect: answers {defect.status} {defect.message!r}")
                if defect.why:
                    lines.append(f"      why: {defect.why}")
        return "\n".join(lines)


def _expr(value: object) -> str:
    if isinstance(value, date):
        return f"date({value.year}, {value.month}, {value.day})"
    if isinstance(value, Fixture):
        given = ", ".join(f"{k}={_expr(v)}" for k, v in vars(value).items() if v is not None)
        return f"{type(value).__name__}({given})"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{k!r}: {_expr(v)}" for k, v in value.items()) + "}"
    return repr(value)


def _loose(raw: bytes) -> object:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return raw


def _known(value: object, know: Callable[[Reference], Any] | None) -> object:
    return know(value) if isinstance(value, Reference) and know is not None else value


def _id_values(shape: Shape | None, value: Any, where: str, out: list[tuple[str, Id, str]]) -> None:
    if isinstance(value, Reference) or value is None:
        return
    if isinstance(shape, Id):
        out.append((where, shape, str(value)))
    elif isinstance(value, dict) and isinstance(shape, Object):
        for k, v in value.items():
            if k in shape.fields:
                _id_values(shape.fields[k].shape, v, f"{where}.{k}", out)
    elif isinstance(value, list) and isinstance(shape, List):
        for v in value:
            _id_values(shape.of, v, f"{where}[]", out)


def opaque_fields(shape: Shape | None, where: str = "", seen: set[int] | None = None) -> list[tuple[str, str]]:
    seen = seen if seen is not None else set()
    if shape is None or id(shape) in seen:
        return []
    seen.add(id(shape))
    if isinstance(shape, List):
        return opaque_fields(shape.of, where + "[]", seen)
    if not isinstance(shape, Object):
        return []
    out: list[tuple[str, str]] = []
    for name, spec in shape.fields.items():
        path = f"{where}.{name}" if where else name
        if spec.opaque:
            out.append((path, spec.opaque))
        out += opaque_fields(spec.shape, path, seen)
    return out


class Canon(dict):
    """One answer in the form both sides are compared in."""

    def __str__(self) -> str:
        return "{" + ", ".join(f"{k}: {v}" for k, v in self.items()) + "}"


def canonical(shape: Shape | None, value: Any, *, app: bool, ids: Identities | None, where: str) -> Any:
    """The one form an answer is compared in. The app's side reads the body; the
    model's side reads the view, each field off the attribute it names. An id
    is the model's id, so the app's id goes back through the registry."""
    if isinstance(shape, Id):
        if value is None:
            return None
        if not app:
            return str(value)
        found = ids.model_of(shape.kind, str(value)) if ids is not None else None
        if found is not None:
            return found
        return str(value) if shape.strangers else Unknown(f"unknown {shape.kind.__name__} id {value}")
    if isinstance(shape, List):
        items = [canonical(shape.of, v, app=app, ids=ids, where=f"{where}[]") for v in value]
        if app:
            items = [item for item in items if not _unknown(item)]
        if shape.unordered:
            items.sort(key=str)
        return tuple(items)
    if isinstance(shape, Object):
        out = Canon()
        for name, spec in shape.fields.items():
            if spec.opaque:
                if spec.required and not spec.nullable:
                    continue
                if app:
                    got = value.get(name)
                elif hasattr(value, spec.reads or attribute(name)):
                    got = getattr(value, spec.reads or attribute(name))
                else:
                    continue
                out[name] = None if got is None else SET
                continue
            if app:
                got = value.get(name)
            else:
                held = spec.reads or attribute(name)
                if not hasattr(value, held):
                    raise BookError(f"{where}.{name}: the model's view carries no {held!r} and the field is not opaque")
                got = getattr(value, held)
            out[name] = None if got is None else canonical(spec.shape, got, app=app, ids=ids, where=f"{where}.{name}")
        return out
    if isinstance(shape, Bytes):
        return value[:len(shape.starts)]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


SET = "<set, value not compared>"


class Unknown(str):
    pass


def _unknown(value: Any) -> bool:
    if isinstance(value, Unknown):
        return True
    if isinstance(value, dict):
        return any(_unknown(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_unknown(v) for v in value)
    return False


def _id_fields(shape: Shape | None, where: str, out: list[tuple[str, Id]], seen: set[int] | None = None) -> None:
    seen = seen if seen is not None else set()
    if shape is None or id(shape) in seen:
        return
    seen.add(id(shape))
    if isinstance(shape, Id):
        out.append((where, shape))
    elif isinstance(shape, List):
        _id_fields(shape.of, where + "[]", out, seen)
    elif isinstance(shape, Object):
        for name, spec in shape.fields.items():
            _id_fields(spec.shape, f"{where}.{name}" if where else name, out, seen)


def identity_lines(endpoints: Iterable[type[Endpoint]], only: type[Endpoint] | None = None) -> list[str]:
    """Per record kind, the answers that produce its id and the inputs that consume it."""
    produced: dict[type, list[str]] = {}
    consumed: dict[type, list[str]] = {}
    for endpoint in endpoints:
        if only is not None and endpoint is not only:
            continue
        found: list[tuple[str, Id]] = []
        for answer in endpoint.answers:
            if succeeded(answer.status):
                _id_fields(answer.body, "", found)
                for where, shape in found:
                    produced.setdefault(shape.kind, []).append(f"{endpoint.__name__} {answer.status} {where}")
                found = []
        for place, shape in (("path", endpoint.params), ("query", endpoint.query), ("body", endpoint.body)):
            _id_fields(shape, "", found)
            for where, kind in found:
                consumed.setdefault(kind.kind, []).append(f"{endpoint.__name__} {place} {where}")
            found = []
    out: list[str] = []
    for kind in sorted({*produced, *consumed}, key=lambda k: k.__name__):
        out.append(f"id of {kind.__name__}")
        out.append("    produced by: " + (", ".join(dict.fromkeys(produced.get(kind, []))) or "nothing"))
        out.append("    consumed by: " + (", ".join(dict.fromkeys(consumed.get(kind, []))) or "nothing"))
    return out


def bare_ids(shape: Shape | None, where: str, seen: set[int] | None = None) -> list[str]:
    """The fields that look like an identifier but are typed as plain text."""
    seen = seen if seen is not None else set()
    if shape is None or id(shape) in seen:
        return []
    seen.add(id(shape))
    if isinstance(shape, List):
        return bare_ids(shape.of, where + "[]", seen)
    if not isinstance(shape, Object):
        return []
    out: list[str] = []
    for name, spec in shape.fields.items():
        named = name == "id" or name.endswith("Id") or name.endswith("_id")
        if named and type(spec.shape) is Str:
            out.append(f"{where}.{name}: looks like an identifier but is typed Str, not Id")
        out += bare_ids(spec.shape, f"{where}.{name}", seen)
    return out


def _prepared(shape: Shape | None, value: Any, ids: Identities | None, know: Callable[[Reference], Any] | None,
              where: str) -> Any:
    """The body as it goes on the wire: references resolved, and every id the
    shape types as an Id turned into the app's id of that kind."""
    if isinstance(value, Reference):
        return _known(value, know)
    if isinstance(shape, Id):
        return value if value is None else real_id(shape, value, ids, where)
    if isinstance(value, dict):
        fields = shape.fields if isinstance(shape, Object) else {}
        return {k: _prepared(fields[k].shape if k in fields else (shape.of if isinstance(shape, Map) else None), v, ids, know, f"{where}.{k}")
                for k, v in value.items()}
    if isinstance(value, list):
        return [_prepared(shape.of if isinstance(shape, List) else None, v, ids, know, f"{where}[]") for v in value]
    return value


def _wire(value: object, shape: Shape | None = None) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(shape, Object) and is_dataclass(value) and not isinstance(value, type):
        return shape.pack(value)
    if isinstance(shape, List) and isinstance(value, (list, tuple)):
        return [_wire(item, shape.of) for item in cast("list[object]", value)]
    return value


def named_shapes(endpoints: tuple[type[Endpoint], ...]) -> dict[str, Object]:
    out: dict[str, Object] = {}

    def visit(shape: Shape | None) -> None:
        if isinstance(shape, Object) and shape.name:
            out.setdefault(shape.name, shape)
            for f in shape.fields.values():
                visit(f.shape)
        elif isinstance(shape, (List, Map)):
            visit(shape.of)

    for endpoint in endpoints:
        visit(endpoint.body if not isinstance(endpoint.body, Bytes) else None)
        for answer in endpoint.answers:
            visit(answer.body)
    return out


def _as_values(query: Mapping[str, object] | Fixture | None) -> dict[str, object]:
    if query is None:
        return {}
    if isinstance(query, Fixture):
        return {k: v for k, v in vars(query).items() if v is not None}
    return dict(query)
