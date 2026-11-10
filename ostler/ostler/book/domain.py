"""The declarative model: a state made of collections, actions that reduce a
request to primitive changes on it, and the fixtures a journey hands around.

A service declares its state as a class whose attributes are `Collection`s and
whose subclasses are the states the app can be in, each with the rules it
refuses every request by. It declares an action as a class: what it accepts,
the rules it checks in order, and `reduce`, one typed function from the
accepted input and the state to the primitives ostler owns: `Create`, `Update`,
`Delete`, `Become`, `MoveToday`, grouped in a `Transaction`, or a `Select` and
a `Show` for a read. A request names the action it carries; `State.apply`
dispatches, applies the primitives and keeps the log a reader traces.
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import date
from typing import Any, Callable, ClassVar, Generic, Hashable, Iterable, Iterator, Mapping, Self, TypeVar, cast

from ostler.book.cast import SOLE, Actor
from ostler.book.errors import BookError
from ostler.book.outcome import Done, Flawed, Refusal
from ostler.book.model import A, Defect, Flaw, Model, Refused, Rule, S

T = TypeVar("T")


class Fixture:
    """What a journey writes down once and hands to every step that touches it:
    the external model, as the surface accepts it. A dataclass subclass declares
    the fields; the service fills in the id it generates."""

    def set(self, **fields: Any) -> Self:
        """Change this fixture in place and hand it back: the client's picture of
        the thing moved on."""
        for name, value in fields.items():
            if not hasattr(self, name):
                raise BookError(f"{type(self).__name__} has no field {name!r}")
            setattr(self, name, value)
        return self

    def but(self, **fields: Any) -> Self:
        """A copy with these fields changed and the same id: one attempt, which
        leaves this fixture as it was whether the service takes it or not."""
        return copy.deepcopy(self).set(**fields)

    @classmethod
    def of(cls, entity: object, **fields: Any) -> Self:
        """The fixture that stands for a stored entity: every field the two
        share, read off the entity."""
        shared = {name: getattr(entity, name) for name in cls.field_names() if hasattr(entity, name)}
        shared.update(fields)
        return cls(**shared)

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Self]:
        """The fixtures `explore` tries from this state for this caller, when the
        derived ones cannot be built: a body that needs records the state keeps,
        a recipient. A class that overrides this replaces the derived variants."""
        return ()

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in dataclasses.fields(cast(Any, cls)))


@dataclasses.dataclass(frozen=True)
class On(Fixture):
    """What a call carries when its target and its body are different things.
    A subclass may be an action's `accept` and give `examples`: the call then
    reaches `explore`, and the action receives the subclass."""

    target: object
    body: object


@dataclasses.dataclass(frozen=True)
class Heard(Fixture):
    """What a call carries when the service also reads request headers: the
    thing the call is about, and the headers it sent. An action that sets
    `hears` receives this and reduces over both."""

    of: object  # pyright: ignore[reportIncompatibleMethodOverride]
    headers: tuple[tuple[str, object], ...] = ()

    def header(self, name: str, default: object = None) -> object:
        for key, value in self.headers:
            if key.lower() == name.lower() and value is not None:
                return value
        return default


@dataclasses.dataclass(frozen=True)
class App:
    """The app a book describes: the directories under its root that hold
    behaviour, the paths no element names, and the file that records the commit
    the book was last verified against."""

    roots: tuple[str, ...]
    verified: str
    ignore: tuple[str, ...] = ("*_test.go", "mocks/*", "*/testdata/*")


@dataclasses.dataclass(frozen=True)
class Unique:
    """The fields that identify one entity in a collection. Exactly one per collection."""

    fields: tuple[str, ...]

    def __init__(self, *fields: str):
        object.__setattr__(self, "fields", fields)


@dataclasses.dataclass(frozen=True)
class Index:
    """Fields the collection can be asked by, beyond its unique key."""

    fields: tuple[str, ...]

    def __init__(self, *fields: str):
        object.__setattr__(self, "fields", fields)


class Collection(Generic[T]):
    """The entities of one kind the state keeps, in the order they were created,
    found by the unique key and asked by the declared indexes. Only a primitive
    changes it."""

    def __init__(self, of: type[T], *indexes: Unique | Index):
        unique = [i for i in indexes if isinstance(i, Unique)]
        if len(unique) != 1:
            raise BookError(f"a collection of {of.__name__} needs exactly one Unique index, got {len(unique)}")
        self.of = of
        self.unique = unique[0]
        self.indexes = tuple(indexes)
        self.name = of.__name__.lower()
        self.items: dict[Hashable, T] = {}

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def fresh(self) -> Collection[T]:
        twin = Collection(self.of, *self.indexes)
        twin.name = self.name
        return twin

    def copy(self) -> Collection[T]:
        twin = self.fresh()
        twin.items = dict(self.items)
        return twin

    def key_of(self, entity: object) -> Hashable:
        values = tuple(getattr(entity, f, None) for f in self.unique.fields)
        if any(v is None for v in values):
            raise BookError(f"a {self.of.__name__} with no {'/'.join(self.unique.fields)} cannot be kept")
        return values[0] if len(values) == 1 else values

    def asked_by(self) -> set[str]:
        return {f for index in self.indexes for f in index.fields}

    def where(self, **by: object) -> list[T]:
        """The entities whose indexed fields hold these values."""
        unknown = set(by) - self.asked_by()
        if unknown:
            raise BookError(f"{self.name} has no index on {sorted(unknown)}")
        return [e for e in self.items.values() if all(getattr(e, f) == v for f, v in by.items())]

    def get(self, key: Hashable) -> T | None:
        return self.items.get(key)

    def position(self, key: Hashable) -> int:
        return list(self.items).index(key)

    def __contains__(self, key: object) -> bool:
        return key in self.items

    def __getitem__(self, key: Hashable) -> T:
        return self.items[key]

    def __iter__(self) -> Iterator[T]:
        return iter(self.items.values())

    def __len__(self) -> int:
        return len(self.items)

    def __str__(self) -> str:
        return self.name


class Change:
    """A primitive the state applies. The service writes none; it composes these."""

    def apply(self, state: State) -> None:
        raise NotImplementedError

    def brief(self) -> str:
        """The change without its values: what kind, on which collection."""
        raise NotImplementedError


@dataclasses.dataclass(frozen=True, eq=False)
class Create(Change):
    collection: Collection[Any]
    entity: object

    def apply(self, state: State) -> None:
        collection = state.own(self.collection)
        key = collection.key_of(self.entity)
        if key in collection:
            raise BookError(f"{collection.name} already keeps {key!r}")
        collection.items[key] = self.entity

    def __str__(self) -> str:
        return f"create {self.collection.name} {self.entity}"

    def brief(self) -> str:
        return f"create {self.collection.name}"


@dataclasses.dataclass(frozen=True, eq=False)
class Update(Change):
    collection: Collection[Any]
    key: Hashable
    entity: object

    def apply(self, state: State) -> None:
        collection = state.own(self.collection)
        if self.key not in collection:
            raise BookError(f"{collection.name} keeps no {self.key!r} to update")
        if collection.key_of(self.entity) != self.key:
            raise BookError(f"an update may not change the key of {self.key!r}")
        collection.items[self.key] = self.entity

    def __str__(self) -> str:
        return f"update {self.collection.name} {self.entity}"

    def brief(self) -> str:
        return f"update {self.collection.name}"


@dataclasses.dataclass(frozen=True, eq=False)
class Delete(Change):
    collection: Collection[Any]
    key: Hashable

    def apply(self, state: State) -> None:
        collection = state.own(self.collection)
        if self.key not in collection:
            raise BookError(f"{collection.name} keeps no {self.key!r} to delete")
        del collection.items[self.key]

    def __str__(self) -> str:
        return f"delete {self.collection.name} [{str(self.key)[:8]}]"

    def brief(self) -> str:
        return f"delete {self.collection.name}"


@dataclasses.dataclass(frozen=True, eq=False)
class Become(Change):
    """The app moves to another of its states; the collections stay."""

    state: type[State]

    def apply(self, state: State) -> None:
        state.__class__ = self.state

    def __str__(self) -> str:
        return f"become {self.state.__name__}"

    def brief(self) -> str:
        return str(self)


@dataclasses.dataclass(frozen=True, eq=False)
class MoveToday(Change):
    today: date

    def apply(self, state: State) -> None:
        state.today = self.today

    def __str__(self) -> str:
        return f"today becomes {self.today.isoformat()}"

    def brief(self) -> str:
        return "today moves"


class Transaction:
    """Changes applied together, in order."""

    def __init__(self, *changes: Change):
        self.changes = changes

    def __str__(self) -> str:
        return "; ".join(str(c) for c in self.changes) or "nothing changes"


@dataclasses.dataclass(frozen=True)
class Total:
    """What a grouped read returns for one group."""

    key: Any
    value: Any


@dataclasses.dataclass(frozen=True, eq=False)
class Select(Generic[T]):
    """A read: the entities of a collection a predicate keeps, in the order a key
    sorts them. With `group`, one `Total` per group: the sum of `total(e)`, or the
    count when `total` is None, sorted by key unless `order` sorts the totals."""

    collection: Collection[T]
    where: Callable[[T], bool] | None = None
    order: Callable[[Any], Any] | None = None
    group: Callable[[T], Any] | None = None
    total: Callable[[T], Any] | None = None

    def run(self, state: State) -> list[Any]:
        found = [e for e in state.own(self.collection) if self.where is None or self.where(e)]
        if self.group is not None:
            sums: dict[Any, Any] = {}
            for e in found:
                key = self.group(e)
                sums[key] = sums.get(key, 0) + (self.total(e) if self.total is not None else 1)
            totals = [Total(key, value) for key, value in sums.items()]
            return sorted(totals, key=self.order if self.order is not None else lambda t: t.key)
        return sorted(found, key=self.order) if self.order is not None else found

    def __str__(self) -> str:
        return f"select {self.collection.name}"


class Show:
    """A read of something that is not a collection: a value the user is shown."""

    def __init__(self, *values: object):
        self.values = values

    def __str__(self) -> str:
        return "show " + ", ".join(str(v) for v in self.values)


Reduced = Transaction | Change | Select[Any] | Show | None


class Action(Generic[A, S]):
    """One thing the domain does. The class body is the whole definition:
    what it accepts, the rules it checks in order, and `reduce`."""

    accept: ClassVar[type[Any] | None] = None
    hears: ClassVar[bool] = False
    rules: ClassVar[tuple[Rule[Any, Any], ...]] = ()
    defects: ClassVar[tuple[Defect[Any, Any], ...]] = ()

    @staticmethod
    def reduce(a: A, s: S, by: Actor | None) -> Reduced:
        return None

    @classmethod
    def take(cls, raw: object) -> A:
        if isinstance(raw, Heard):
            if not cls.hears:
                raise BookError(f"{cls.__name__} does not hear headers but the call declares them: set hears = True")
            return cast(A, Heard(cls.listen(raw.of), raw.headers))
        if cls.hears:
            return cast(A, Heard(cls.listen(raw), ()))
        return cls.listen(raw)

    @classmethod
    def listen(cls, raw: object) -> A:
        if cls.accept is None:
            return cast(A, raw)
        if isinstance(raw, cls.accept):
            return cast(A, raw)
        if isinstance(raw, On) and issubclass(cls.accept, On):
            return cast(A, cls.accept(raw.target, raw.body))
        if isinstance(raw, Mapping):
            try:
                return cast(A, cls.accept(**cast(Mapping[str, object], raw)))
            except TypeError as wrong:
                raise BookError(f"{cls.__name__} accepts a {cls.accept.__name__}: {wrong}") from None
        raise BookError(f"{cls.__name__} accepts a {cls.accept.__name__}, not {type(raw).__name__}")

    @classmethod
    def perform(cls, raw: object, state: S, by: Actor | None) -> Reduced:
        accepted = cls.take(raw)
        for rule in cls.rules:
            try:
                rule.check(accepted, state, by)
            except Refused as refused:
                for defect in cls.defects:
                    if defect.over is rule and defect.shows(accepted, state, by):
                        raise Flaw(defect, None, rule, cls.wrong(defect, accepted, state, by), refused.said) from None
                raise
        reduced = cls.reduce(accepted, state, by)
        for defect in cls.defects:
            if defect.over is None and defect.shows(accepted, state, by):
                raise Flaw(defect, reduced, None, cls.wrong(defect, accepted, state, by))
        return reduced

    @staticmethod
    def wrong(defect: Defect[Any, Any], accepted: object, state: Any, by: Actor | None) -> Reduced:
        return defect.does(accepted, state, by) if defect.does is not None else None

    @classmethod
    def explain(cls) -> str:
        lines = [f"{cls.__name__}: accepts " + (cls.accept.__name__ if cls.accept else "nothing")]
        for rule in cls.rules:
            lines.append(f"  refuses {rule.status} {rule.message!r}")
            if rule.why:
                lines.append(f"    why: {rule.why}")
        for defect in cls.defects:
            meant = f"where {defect.over.status} {defect.over.message!r} is meant" if defect.over else "where it means to succeed"
            lines.append(f"  known defect: answers {defect.status} {defect.message!r} {meant}")
            if defect.why:
                lines.append(f"    why: {defect.why}")
        return "\n".join(lines)


@dataclasses.dataclass(frozen=True, eq=False)
class Entry:
    """One line of the log: the request and what it reduced to."""

    request: object
    result: Reduced | Refused | Flaw

    def __str__(self) -> str:
        return f"{self.request}\n   {self.result if self.result is not None else 'nothing changes'}"


class State(Model):
    """The app's state: the collections declared on the class, the day it
    believes it is, and the rules this state refuses every request by. A
    subclass per state the app can be in; `Become` moves between them."""

    rules: ClassVar[tuple[Rule[Any, Any], ...]] = ()

    def __init__(self, today: date):
        super().__init__(today)
        self.log: list[Entry] = []
        self.view: tuple[object, ...] | None = None
        for name, declared in self.collections().items():
            setattr(self, name, declared.fresh())

    @classmethod
    def collections(cls) -> dict[str, Collection[Any]]:
        out: dict[str, Collection[Any]] = {}
        for klass in reversed(cls.__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, Collection):
                    out[name] = value
        return out

    def own(self, collection: Collection[T]) -> Collection[T]:
        """This state's instance of a collection, whichever state built the primitive."""
        return getattr(self, collection.name)

    def lookup(self, fixture: object) -> object | None:
        """The entity a fixture stands for, by its unique key, in whichever collection keeps it."""
        for name in self.collections():
            collection: Collection[Any] = getattr(self, name)
            try:
                key = collection.key_of(fixture)
            except BookError:
                continue
            if key in collection:
                return collection[key]
        return None

    def copy(self) -> Self:
        twin = copy.copy(self)
        twin.log = []
        for name in self.collections():
            setattr(twin, name, getattr(self, name).copy())
        return twin

    def apply(self, request: object) -> tuple[object, ...] | None:
        try:
            result = self.dispatch(request)
        except (Refused, Flaw) as stopped:
            self.log.append(Entry(request, stopped))
            raise
        self.log.append(Entry(request, result))
        return self.commit(result)

    def dispatch(self, request: object) -> Reduced:
        kind = type(request)
        by: Actor | None = getattr(request, "by", SOLE)
        for gate in getattr(kind, "gates", ()):
            gate.check(request, self, by)
        for rule in type(self).rules:
            rule.check(request, self, by)
        action: type[Action[Any, Any]] | None = getattr(kind, "carries", None)
        if action is None:
            raise BookError(f"{kind.__name__} carries no action on the model")
        return action.perform(cast(Any, request).input(), self, by)

    def meant(self, flaw: Flaw) -> Done | Refusal:
        if flaw.refused is not None:
            return Refusal(flaw.said, flaw.refused.status)
        twin = self.copy()
        shown = twin.commit(cast(Reduced, flaw.reduced))
        return Done(twin.rows() if shown is None else shown)

    def adopt(self, flawed: Flawed) -> None:
        self.commit(flawed.reduced)

    def undergo(self, flawed: Flawed) -> None:
        self.commit(flawed.wrong)

    def commit(self, result: Reduced) -> tuple[object, ...] | None:
        self.view = None
        if isinstance(result, Transaction):
            for change in result.changes:
                change.apply(self)
            written = [c.entity for c in result.changes if isinstance(c, (Create, Update))]
            self.view = (self.row(written[-1]),) if written else None
        elif isinstance(result, Change):
            result.apply(self)
            if isinstance(result, (Create, Update)):
                self.view = (self.row(result.entity),)
        elif isinstance(result, Select):
            self.view = tuple(self.row(e) for e in result.run(self))
            return self.view
        elif isinstance(result, Show):
            self.view = result.values
            return result.values
        return None

    def describe(self) -> str:
        head = f"{type(self).__name__} · today {self.today.isoformat()}"
        lines = [head]
        for name in self.collections():
            collection: Collection[Any] = getattr(self, name)
            lines.append(f"  {name} ({len(collection)})")
            lines += [f"    {e}" for e in collection]
        return "\n".join(lines)
