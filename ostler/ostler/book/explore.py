"""Every call the declarations allow, derived from them: the endpoints say what
a call carries, the shapes say what each field may hold, the store says what
exists to be pointed at. Nothing here is written by hand per service.

`attempts` lists every variation, valid and not, for the denied listing.
`moves` keeps the valid ones, for the planner.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Iterable, Iterator, Mapping, TypeGuard, cast

from ostler.book.cast import SOLE, Actor
from ostler.book.domain import Action, Fixture, State
from ostler.book.model import Model, attribute
from ostler.book.errors import BookError
from ostler.book.http import Bool, Bytes, Endpoint, Enum, Field, Int, List, Object, Str, unknown_value

DEFAULT_TEXT = "Water the plants"
UNKNOWN_CHOICE = "nobody"


@dataclass(frozen=True)
class Variant:
    fields: dict[str, Any]
    valid: bool


def _valid_values(field: Field, store: Model, wanted: tuple[str, ...]) -> list[Any]:
    shape = field.shape
    if isinstance(shape, Str) and getattr(shape, "format", None) == "date":
        return [store.today + timedelta(days=1), store.today]
    if isinstance(shape, Str):
        return list(wanted) or [DEFAULT_TEXT]
    if isinstance(shape, Enum):
        return list(shape.values)
    if isinstance(shape, Bool):
        return [True, False]
    if isinstance(shape, Int):
        return [1]
    return [None]


def _invalid_values(field: Field, store: Model) -> list[Any]:
    shape = field.shape
    out: list[Any] = []
    if isinstance(shape, Str) and getattr(shape, "format", None) == "date":
        out += [store.today - timedelta(days=1), "next tuesday"]
    elif isinstance(shape, Str):
        out.append("   ")
        max_len = getattr(shape, "max_len", None)
        if max_len:
            out.append("x" * (max_len + 1))
    elif isinstance(shape, Enum):
        out.append(UNKNOWN_CHOICE)
    elif isinstance(shape, Int):
        out.append(-1)
    if not field.nullable:
        out.append(None)
    return out


def variants(shape: Object | List | Bytes | None, store: Model, wanted: tuple[str, ...]) -> list[Variant]:
    """The baseline (every required field at its first valid value) and one
    change at a time from it, each marked valid or not."""
    if not isinstance(shape, Object):
        return [Variant({}, True)]
    baseline = {name: _valid_values(f, store, wanted)[0] for name, f in shape.fields.items() if f.required}
    out = [Variant(baseline, True)]
    for name, f in shape.fields.items():
        for value in _valid_values(f, store, wanted):
            if baseline.get(name, object()) != value:
                out.append(Variant({**baseline, name: value}, True))
        out.append(Variant({**baseline, name: None}, f.nullable))
        for value in _invalid_values(f, store):
            out.append(Variant({**baseline, name: value}, False))
    return _unique(out)


def _unique(items: list[Variant]) -> list[Variant]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = repr(sorted(item.fields.items(), key=lambda kv: kv[0]))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _action_of(endpoint: type[Endpoint]) -> type[Action[Any, Any]] | None:
    return endpoint.carries


def _targets(endpoint: type[Endpoint], store: Model) -> list[object]:
    names = tuple(endpoint.params.fields)
    found = []
    for collection in (getattr(store, n) for n in cast(State, store).collections()):
        for entity in collection:
            if all(hasattr(entity, n) for n in names):
                found.append(entity)
    return found


def _build(endpoint: type[Endpoint], accept: type | None, entity: object | None, fields: Mapping[str, Any],
           **extra: Any) -> object:
    if accept is None:
        return None
    if not issubclass(accept, Fixture):
        return {**fields, **extra}
    named = {attribute(name): value for name, value in {**fields, **extra}.items()}
    try:
        if entity is not None:
            return accept.of(entity, **named)
        return accept(**named)
    except TypeError:
        have = {*fields, *extra, *(n for n in accept.field_names() if entity is not None and hasattr(entity, n))}
        missing = [f.name for f in dataclasses.fields(cast(Any, accept))
                   if f.name not in have and f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING]
        raise BookError(f"{accept.__name__} cannot be built for {endpoint.__name__}: the endpoint declares "
                        f"nothing for {', '.join(missing) or 'some field'}; give the fixture `examples`") from None


def _overrides(accept: type | None) -> TypeGuard[type[Fixture]]:
    return (accept is not None and isinstance(accept, type) and issubclass(accept, Fixture)
            and accept.examples.__func__ is not Fixture.examples.__func__)


def _calls(endpoint: type[Endpoint], store: Model, wanted: tuple[str, ...], every: bool,
           cast: tuple[Actor, ...]) -> Iterator[Endpoint]:
    accept = getattr(_action_of(endpoint), "accept", None)
    is_query = endpoint.query is not None and endpoint.body is None
    carried = variants(endpoint.body or endpoint.query, store, wanted)
    for n, by in enumerate(cast):
        mine = carried if not every or n == 0 else carried[:1]
        if not every:
            mine = [v for v in mine if v.valid]
        if _overrides(accept):
            for example in accept.examples(store, by):
                yield from _one(endpoint, example, is_query=is_query, by=by)
        elif endpoint.params.fields:
            targets = _targets(endpoint, store)
            for entity in targets:
                for variant in mine:
                    yield from _one(endpoint, _build(endpoint, accept, entity, variant.fields), by=by)
            if every and n == 0 and (targets or not endpoint.body):
                stranger = _build(endpoint, accept, None, carried[0].fields, **{p: unknown_value(endpoint.params.fields[p].shape) for p in endpoint.params.fields})
                yield from _one(endpoint, stranger, by=by)
        else:
            for variant in mine:
                yield from _one(endpoint, _build(endpoint, accept, None, variant.fields), is_query=is_query, by=by)
    if every and endpoint.auth and cast:
        if _overrides(accept):
            first = next(iter(accept.examples(store, cast[0])), None)
        else:
            targets = _targets(endpoint, store) if endpoint.params.fields else []
            if accept is None:
                first = None
            elif targets or not endpoint.params.fields:
                first = _build(endpoint, accept, targets[0] if targets else None, carried[0].fields)
            else:
                first = _build(endpoint, accept, None, carried[0].fields, **{p: unknown_value(endpoint.params.fields[p].shape) for p in endpoint.params.fields})
        if accept is None or first is not None:
            yield from _one(endpoint, first, is_query=is_query, by=None)


def _one(endpoint: type[Endpoint], built: object, is_query: bool = False, **kw: Any) -> Iterator[Endpoint]:
    try:
        if built is None:
            yield endpoint(**kw)
        elif is_query:
            yield endpoint(query=built if isinstance(built, Fixture) else cast(Mapping[str, object], built), **kw)
        else:
            yield endpoint(built, **kw)
    except BookError:
        return


def attempts(endpoints: Iterable[type[Endpoint]], store: Model, wanted: tuple[str, ...] = (),
             cast: tuple[Actor, ...] = (SOLE,)) -> list[Endpoint]:
    """Every call the declarations allow from this state, valid or not: the
    baseline of each endpoint for every caller of the cast, the field variations
    for the first, and one call with no caller where the endpoint declares auth."""
    return [call for e in endpoints if e.carries is not None for call in _calls(e, store, wanted, True, cast)]


def moves(endpoints: Iterable[type[Endpoint]], wanted: tuple[str, ...] = (),
          cast: tuple[Actor, ...] = (SOLE,)) -> Callable[[Model], list[Endpoint]]:
    """The valid calls from a state, for every caller of the cast, using these
    texts where a field wants one."""
    kinds = tuple(e for e in endpoints if e.carries is not None)

    def from_state(store: Model) -> list[Endpoint]:
        return [call for e in kinds for call in _calls(e, store, wanted, False, cast)]

    return from_state
