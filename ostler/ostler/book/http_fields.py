from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping

from ostler.book.contracts import STREAMING
from ostler.book.domain import Action, Fixture
from ostler.book.entries import says
from ostler.book.http_canon import _known, opaque_fields
from ostler.book.http_identities import Identities, Reference, wired
from ostler.book.http_objects import Field, List, Object
from ostler.book.http_shapes import Bytes, Id, Map, Shape, Str, Token
from ostler.book.status import succeeded

if TYPE_CHECKING:
    from ostler.book.http_endpoint import Endpoint


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


def token_fields(shape: Shape | None, where: str, out: list[tuple[str, Token, Field]], seen: set[int] | None = None) -> None:
    """Every field of the shape typed Token, with its path and its declaration."""
    seen = seen if seen is not None else set()
    if shape is None or id(shape) in seen:
        return
    seen.add(id(shape))
    if isinstance(shape, (List, Map)):
        token_fields(shape.of, where + "[]", out, seen)
    elif isinstance(shape, Object):
        for name, spec in shape.fields.items():
            path = f"{where}.{name}" if where else name
            if isinstance(spec.shape, Token):
                out.append((path, spec.shape, spec))
            token_fields(spec.shape, path, out, seen)


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
        if value is None or (isinstance(shape.of, Str) and not isinstance(value, str)):
            return value
        return wired(shape, value, ids, where)
    if isinstance(shape, Token):
        return wired(shape, value, ids, where)
    if isinstance(value, dict):
        fields = shape.fields if isinstance(shape, Object) else {}
        sent = {k: _prepared(fields[k].shape if k in fields else (shape.of if isinstance(shape, Map) else None), v, ids, know, f"{where}.{k}")
                for k, v in value.items()}
        return {k: v for k, v in sent.items() if v is not None or not isinstance(fields[k].shape if k in fields else None, Token)}
    if isinstance(value, list):
        return [_prepared(shape.of if isinstance(shape, List) else None, v, ids, know, f"{where}[]") for v in value]
    return value


def named_shapes(endpoints: tuple[type[Endpoint], ...]) -> dict[str, Object]:
    out: dict[str, Object] = {}
    visited: set[int] = set()

    def visit(shape: Shape | None) -> None:
        if isinstance(shape, Object) and shape.name:
            if id(shape) in visited:
                return
            visited.add(id(shape))
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


def describe_endpoint(cls: type[Endpoint]) -> str:
    lines = [cls.route(), f"  {cls.does}"]
    if cls.streams:
        lines.append(f"  {STREAMING[cls.streams]}")
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
            if defect.breaks is not None:
                lines.append(f"    known defect: breaks {says(defect.breaks)}: {defect.message!r}")
            else:
                lines.append(f"    known defect: answers {defect.status} {defect.message!r}")
            if defect.why:
                lines.append(f"      why: {defect.why}")
    return "\n".join(lines)
