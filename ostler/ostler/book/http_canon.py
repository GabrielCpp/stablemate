from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Callable, Mapping

from ostler.book.domain import Fixture
from ostler.book.errors import BookError
from ostler.book.http_identities import Identities, Reference
from ostler.book.http_objects import List, Object
from ostler.book.http_shapes import Bytes, Id, Map, Shape, Token
from ostler.book.model import attribute


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


class Page(str):
    """A page token in the compared form: any two are equal, so only whether a token is there is compared. `app` says
    whose it is."""

    app: bool

    def __new__(cls, text: str, app: bool) -> Page:
        held = super().__new__(cls, text)
        held.app = app
        return held

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Page)

    def __ne__(self, other: object) -> bool:
        return not isinstance(other, Page)

    def __hash__(self) -> int:
        return 0

    def lacks(self) -> str:
        """Why the other side, which gave no token, differs."""
        if self.app:
            return "the app gave a token and the model says there is no next page"
        return "the model says there is a next page and the app gave no token"


def learn_tokens(shape: Shape | None, model: Any, body: Any, ids: Identities) -> None:
    """The pair of each page token both sides gave: the model's token and the app's, kept under the token's name."""
    if isinstance(shape, Token):
        if isinstance(model, Page) and body not in (None, ""):
            ids.learn_token(shape.name, str(model), str(body))
    elif isinstance(shape, Object) and isinstance(model, dict) and isinstance(body, dict):
        for name, spec in shape.fields.items():
            learn_tokens(spec.shape, model.get(name), body.get(name), ids)
    elif isinstance(shape, List) and isinstance(model, (list, tuple)) and isinstance(body, list) and len(model) == len(body):
        for one, other in zip(model, body):
            learn_tokens(shape.of, one, other, ids)


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
    if isinstance(shape, Token):
        return None if value is None or value == "" else Page(str(value), app)
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


def breaches(shape: Shape | None, value: Any, path: str = "") -> list[tuple[str, Callable[[list[Any]], list[str]], str]]:
    """Each rule a list of the answer breaks, with the path of the list and what broke, judged on the entries the app
    answered, whoever's they are."""
    out: list[tuple[str, Callable[[list[Any]], list[str]], str]] = []
    if isinstance(shape, List) and isinstance(value, list):
        for rule in shape.entries:
            try:
                said = rule(value)
            except Exception as crash:
                said = [f"cannot be judged: {type(crash).__name__}: {crash}"]
            out += [(path + "[]", rule, one) for one in said]
        for item in value:
            out += breaches(shape.of, item, path + "[]")
    elif isinstance(shape, Object) and isinstance(value, dict):
        for name, spec in shape.fields.items():
            if value.get(name) is not None:
                out += breaches(spec.shape, value[name], f"{path}.{name}" if path else name)
    elif isinstance(shape, Map) and isinstance(value, dict):
        for item in value.values():
            out += breaches(shape.of, item, path + "{}")
    return out


def _alone(rule: Callable[[list[Any]], list[str]], entry: Any) -> bool:
    try:
        return bool(rule([entry]))
    except Exception:
        return False


def apart(shape: Shape | None, value: Any, owed: tuple[Callable[[list[Any]], list[str]], ...]) -> Any:
    """The answer without the entries that break, on their own, a rule a known defect covers: they are the defect's, and
    nothing else is judged of them. A rule that only breaks across entries leaves nothing out."""
    if not owed:
        return value
    if isinstance(shape, List) and isinstance(value, list):
        held = [rule for rule in shape.entries if any(rule is covered for covered in owed)]
        return [apart(shape.of, item, owed) for item in value if not any(_alone(rule, item) for rule in held)]
    if isinstance(shape, Object) and isinstance(value, dict):
        return {name: apart(shape.fields[name].shape, item, owed) if name in shape.fields else item for name, item in value.items()}
    if isinstance(shape, Map) and isinstance(value, dict):
        return {name: apart(shape.of, item, owed) for name, item in value.items()}
    return value


def states(shape: Shape | None, rule: Callable[[list[Any]], list[str]], seen: set[int] | None = None) -> bool:
    """Whether a list anywhere in the shape holds the rule among its entries."""
    seen = seen if seen is not None else set()
    if shape is None or id(shape) in seen:
        return False
    seen.add(id(shape))
    if isinstance(shape, List):
        return any(stated is rule for stated in shape.entries) or states(shape.of, rule, seen)
    if isinstance(shape, Object):
        return any(states(spec.shape, rule, seen) for spec in shape.fields.values())
    if isinstance(shape, Map):
        return states(shape.of, rule, seen)
    return False


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
