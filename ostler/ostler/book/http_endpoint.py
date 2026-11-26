from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, ClassVar, Mapping, cast

from ostler.book.boundary import Passes, Reaches
from ostler.book.cast import KEEP, SOLE, Actor
from ostler.book.domain import Action, Fixture, Heard, On
from ostler.book.errors import BookError, Unhealthy
from ostler.book.http_canon import (
    _expr,
    _id_values,
    _known,
    _loose,
    apart,
)
from ostler.book.http_fields import _as_values, _prepared, describe_endpoint
from ostler.book.http_identities import Identities, Reference, Reply, wired
from ostler.book.http_objects import Answer, Auth, List, Object, _wire
from ostler.book.http_shapes import Bytes, Id, Token
from ostler.book.http_transport import Client, OffShape, Undeclared
from ostler.book.outcome import Refusals
from ostler.book.signed import Signed
from ostler.book.status import Code, Status, redirected, succeeded

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
    passes: ClassVar[Passes | None] = None
    reaches: ClassVar[Reaches | None] = None
    source: ClassVar[tuple[str, ...]] = ()
    unauthenticated: ClassVar[Status] = 401
    typed_wire: ClassVar[bool] = False
    typed_away: ClassVar[tuple[str, ...]] = ("wrong type", "out of enum", "null")
    streams: ClassVar[str] = ""

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
        if not cls.answers and not cls.streams:
            raise BookError(f"{name}: declares no answer")
        statuses = [a.status for a in cls.answers]
        if len(statuses) != len(set(statuses)):
            raise BookError(f"{name}: a status is declared twice")
        if cls.passes is not None and cls.carries is not None:
            raise BookError(f"{name}: passes the owner's answer on, so it carries no action of its own")
        if cls.reaches is not None and cls.carries is not None:
            raise BookError(f"{name}: reaches the owner's call, so it carries no action of its own")
        if cls.auth and cls.answers and cls.unauthenticated not in statuses:
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
            if value is not None and isinstance(shape, (Id, Token)):
                value = wired(shape, value, ids, f"{cls.__name__} path {name}")
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
            pairs = [(k, _wire(sent)) for k, v in self.query_values.items() if v is not None
                     and (sent := self._query_value(k, v, ids, know)) is not None]
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
        if spec is not None and isinstance(spec.shape, (Id, Token)):
            return wired(spec.shape, value, ids, f"{cls.__name__} query {name}")
        return value

    def payload(self, ids: Identities | None = None, know: Callable[[Reference], Any] | None = None) -> Any:
        cls = type(self)
        if cls.body is None:
            return None
        if isinstance(cls.body, Bytes):
            return self.body_value
        return _prepared(cls.body, cast("Object | List", cls.body).pack(self.body_value), ids, know,
                         f"{cls.__name__} body")

    def exchange(self, client: Client) -> tuple[Status, bytes]:
        """The call carried out: the status the service gave and the bytes of its answer."""
        cls = type(self)
        headers = {"Content-Type": "application/json"}
        for name, value in self.header_values.items():
            if value is not None:
                headers[name] = str(_wire(value))
        if self.auth_used is not None and self.by is not None:
            credential = client.held.get((self.by, self.auth_used))
            if credential is None:
                raise BookError(f"the client holds no {self.auth_used.describe()} for {self.by}")
            name, value = self.auth_used.header(credential.token if isinstance(credential, Signed) else credential)
            headers[name] = value
        payload = self.payload(client.ids, client.resolve)
        if isinstance(payload, bytes):
            data, headers["Content-Type"] = payload, "application/octet-stream"
        else:
            data = None if payload is None else json.dumps(payload).encode()
        return client.transport(cls.method, self.url(client.address(cls.host), client.ids, client.resolve), headers, data)

    def send(self, client: Client, owed: tuple[Callable[[list[Any]], list[str]], ...] = ()) -> Reply:
        cls = type(self)
        status, raw = self.exchange(client)
        answer = next((a for a in cls.answers if a.status == status), None)
        if answer is None and status in GATEWAY:
            raise Unhealthy(f"{cls.route()} answered {status}: the service is not there to answer")
        if answer is None:
            raise Undeclared(cls, status, _loose(raw))
        whole = parsed = None if redirected(status) and answer.body is None else cls.read(answer, raw)
        if answer.body is not None:
            parsed = apart(answer.body, parsed, owed)
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
        self.reply = Reply(status, parsed, answer, lambda body: client.ids.spoken(client.message_of(body)), whole,
                           client.place(getattr(client, "located", "")) if redirected(status) else "")
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
        return describe_endpoint(cls)
