from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, cast

from ostler.book.http_canon import _unknown, canonical
from ostler.book.http_identities import Identities
from ostler.book.http_objects import Answer, Field, List, Object, _real
from ostler.book.http_shapes import Bool, Enum, Int, Map, Num, Shape
from ostler.book.status import Status

if TYPE_CHECKING:
    from ostler.book.http_endpoint import Endpoint


def declared_paths(shape: Shape | None, prefix: str = "", trail: tuple[Object, ...] = ()) -> list[str]:
    """Every field path a shape declares, going through lists as `lines[].quantity`. An object that holds itself declares each
    of its fields once: meeting an object already on the path ends it."""
    if isinstance(shape, Object):
        if any(shape is above for above in trail):
            return []
        out: list[str] = []
        for key, spec in shape.fields.items():
            path = f"{prefix}.{key}" if prefix else key
            out.append(path)
            out += declared_paths(spec.shape, path, (*trail, shape))
        return out
    if isinstance(shape, List):
        return declared_paths(shape.of, prefix + "[]", trail)
    if isinstance(shape, Map):
        return declared_paths(shape.of, prefix + "{}", trail)
    return []


VALUES_KEPT = 2


def has_domain(spec: Field) -> bool:
    return isinstance(spec.shape, (Enum, Bool, Int, Num)) and not spec.opaque and not spec.ignores


def domain_paths(shape: Shape | None, prefix: str = "", trail: tuple[Object, ...] = ()) -> dict[str, Shape]:
    """The declared field paths whose shape has a value domain, an enum, a boolean or a number, and
    that the comparison does not drop, each with its shape."""
    out: dict[str, Shape] = {}
    if isinstance(shape, Object):
        if any(shape is above for above in trail):
            return out
        for key, spec in shape.fields.items():
            path = f"{prefix}.{key}" if prefix else key
            if has_domain(spec):
                out[path] = spec.shape
            out.update(domain_paths(spec.shape, path, (*trail, shape)))
    elif isinstance(shape, (List, Map)):
        out.update(domain_paths(shape.of, prefix + ("[]" if isinstance(shape, List) else "{}"), trail))
    return out


def real_paths(shape: Shape | None, value: object, prefix: str = "", ids: Identities | None = None,
               trail: Mapping[int, str] | None = None, values: dict[str, set[Any]] | None = None) -> set[str]:
    """The declared field paths at which this value holds something real. A list
    entry the comparison drops, one naming an id the book never issued, shows
    nothing: the run did not check it. An object that holds itself folds onto the
    paths `declared_paths` gives: entering an object already on the path
    continues from the prefix it was first entered at."""
    out: set[str] = set()
    trail = trail if trail is not None else {}
    if isinstance(shape, Object) and isinstance(value, dict):
        if id(shape) in trail:
            prefix = trail[id(shape)]
        else:
            trail = {**trail, id(shape): prefix}
        for key, spec in shape.fields.items():
            if _real(value.get(key)):
                path = f"{prefix}.{key}" if prefix else key
                out.add(path)
                if values is not None and has_domain(spec):
                    held = values.setdefault(path, set())
                    if len(held) < VALUES_KEPT:
                        held.add(cast(dict[str, Any], value)[key])
                out |= real_paths(spec.shape, cast(dict[str, Any], value)[key], path, ids, trail, values)
    elif isinstance(shape, List) and isinstance(value, list):
        for item in value:
            if ids is not None and _unknown(canonical(shape.of, item, app=True, ids=ids, where=prefix + "[]")):
                continue
            out |= real_paths(shape.of, item, prefix + "[]", ids, trail, values)
    elif isinstance(shape, Map) and isinstance(value, dict):
        for item in value.values():
            out |= real_paths(shape.of, item, prefix + "{}", ids, trail, values)
    return out


class Witness:
    """What a client has seen the service do: for each endpoint the statuses it
    answered, and for each answer the field paths that held a real value. Real
    is not null, not an empty string, list or object. For a field with a value domain it also keeps
    the first two distinct values it held."""

    def __init__(self) -> None:
        self.statuses: dict[type[Endpoint], set[Status]] = {}
        self._fields: dict[tuple[type[Endpoint], Status], set[str]] = {}
        self._values: dict[tuple[type[Endpoint], Status], dict[str, set[Any]]] = {}
        self._pending: list[tuple[type[Endpoint], Answer, object, Identities | None]] = []

    def see(self, endpoint: type[Endpoint], answer: Answer, body: object, ids: Identities | None = None) -> None:
        self.statuses.setdefault(endpoint, set()).add(answer.status)
        self._pending.append((endpoint, answer, body, ids))

    def settle(self) -> None:
        for endpoint, answer, body, ids in self._pending:
            key = (endpoint, answer.status)
            held = self._values.setdefault(key, {})
            self._fields.setdefault(key, set()).update(real_paths(answer.body, body, "", ids, values=held))
        self._pending.clear()

    @property
    def fields(self) -> dict[tuple[type[Endpoint], Status], set[str]]:
        self.settle()
        return self._fields

    @property
    def values(self) -> dict[tuple[type[Endpoint], Status], dict[str, set[Any]]]:
        self.settle()
        return self._values

    def merge(self, other: Witness) -> None:
        for endpoint, statuses in other.statuses.items():
            self.statuses.setdefault(endpoint, set()).update(statuses)
        for key, paths in other.fields.items():
            self.fields.setdefault(key, set()).update(paths)
        for key, by_path in other.values.items():
            mine = self.values.setdefault(key, {})
            for path, held in by_path.items():
                kept = mine.setdefault(path, set())
                for value in held:
                    if len(kept) < VALUES_KEPT:
                        kept.add(value)
