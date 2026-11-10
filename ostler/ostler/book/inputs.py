"""The input classes of an endpoint, derived from its shapes, and what the run
does with them. A class is one way to fill one input: a valid one the shape
names, or a wrong one the shape implies. Each is sent once, from a call the run
already saw succeed, with every other input as that call had it.

The model says what a class gets when it has a rule for it. When it has none
and the class is wrong, the service's declared default refusal is expected. An
app that accepts what the book refuses is declared with `Diverges`, and why."""

from __future__ import annotations

import copy
import dataclasses
import itertools
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, Mapping, TypeGuard, cast

from ostler.book.backstage import CannotArrange
from ostler.book.cast import Actor
from ostler.book.domain import Fixture
from ostler.book.errors import BookError, Unhealthy
from ostler.book.http import Bool, Client, Endpoint, Enum, Field, Id, Identities, Int, List, Object, OffShape, Str, Undeclared, unknown_value
from ostler.book.journey import StepResult
from ostler.book.model import Defect, Model
from ostler.book.outcome import Done, Flawed, Outcome, Refusal, Refusals
from ostler.book.runner import agree, attempt, listing
from ostler.book.surface import Surface

if TYPE_CHECKING:
    from ostler.book.service import Service

GONE = object()
PLACES = ("path", "query", "body", "headers")
TYPED_AWAY = ("wrong type", "out of enum", "null")


@dataclass(frozen=True)
class Diverges:
    """The app accepts an input class the book refuses. `label` names the class
    as the run prints it, such as "down missing"."""

    endpoint: type[Endpoint]
    label: str
    why: str

    def __post_init__(self) -> None:
        if not self.why.strip():
            raise BookError(f"Diverges {self.endpoint.__name__} {self.label}: say why the app accepts it")

    def __str__(self) -> str:
        return f"{self.endpoint.__name__} {self.label}"


@dataclass(frozen=True)
class InputClass:
    place: str
    name: str
    kind: str
    value: Any
    valid: bool
    default: str = ""
    edits: tuple[tuple[str, Any], ...] = ()

    @property
    def label(self) -> str:
        return f"{self.name} {self.kind}"


def has_inputs(endpoint: type[Endpoint]) -> bool:
    return bool(endpoint.params.fields or endpoint.query or isinstance(endpoint.body, Object) or endpoint.headers)


def _other_kind_id(kind: type, model: Model, ids: Identities | None) -> str | None:
    collections = getattr(model, "collections", None)
    names = collections() if collections is not None else ()
    for name in names:
        collection = getattr(model, name)
        if collection.of is kind:
            continue
        for entity in collection:
            text = str(getattr(entity, "id", ""))
            return (ids.real(collection.of, text) or text) if ids is not None else text
    return None


def _foreign_id(kind: type, model: Model, ids: Identities | None, by: Actor | None, current: Any = None) -> str | None:
    owned_by = getattr(kind, "owned_by", "")
    if not owned_by or by is None:
        return None
    collections = getattr(model, "collections", None)
    names = collections() if collections is not None else ()
    everything = [(getattr(model, name).of, entity) for name in names for entity in getattr(model, name)]
    same = next((type(e) for _, e in everything if current is not None and str(getattr(e, "id", "")) == str(current)), kind)
    found = [(type(entity) is not same, ids is not None and not ids.real(of, str(getattr(entity, "id", ""))), str(getattr(entity, "id", "")))
             for of, entity in everything
             if isinstance(entity, kind) and getattr(entity, owned_by, by.identity) not in ("", None, by.identity)]
    return min(found)[2] if found else None


def _values(call: Endpoint, place: str) -> Mapping[str, Any]:
    cls = type(call)
    if place == "path":
        target = call.of
        if isinstance(target, Mapping):
            return cast(Mapping[str, Any], target)
        if isinstance(target, tuple):
            return dict(zip(cls.params.fields, target)) if isinstance(cls.params, Object) else {}
        if isinstance(cls.params, Object):
            return {n: getattr(target, n, None) for n in cls.params.fields}
        return {}
    if place == "query":
        return call.query_values if isinstance(call.query_values, Mapping) else {}
    if place == "body" and isinstance(cls.body, Object):
        return cls.body.pack(call.body_value)
    return {}


def _wrong_type(shape: Any) -> Any:
    if isinstance(shape, Bool):
        return "yes"
    if isinstance(shape, Int):
        return "many"
    return 123


def field_classes(place: str, name: str, spec: Field, model: Model, ids: Identities | None, by: Actor | None = None,
                  current: Any = None) -> list[InputClass]:
    shape = spec.shape
    if isinstance(shape, Id) and shape.minted:
        return field_classes(place, name, dataclasses.replace(spec, shape=shape.of), model, ids, by, current)
    out: list[InputClass] = []

    def add(kind: str, value: Any, default: str = "", valid: bool = False) -> None:
        out.append(InputClass(place, name, kind, value, valid, default))

    if isinstance(shape, Id):
        if shape.of.check("not-an-id"):
            add("malformed", "not-an-id", "malformed")
        if isinstance(shape.of, Str):
            for label, value in shape.of.near_misses().items():
                add(label, value, "malformed")
        add("unknown", unknown_value(shape), "unknown_id")
        other = _other_kind_id(shape.kind, model, ids)
        if other is not None:
            add("wrong kind", other, "wrong_kind")
        foreign = _foreign_id(shape.kind, model, ids, by, current)
        if foreign is not None:
            add("another owner's", foreign, valid=True)
    elif isinstance(shape, Str):
        for label, value in shape.classes.items():
            add(label, value, valid=True)
        if shape.format == "date":
            add("malformed date", "not a date", "malformed")
        if place == "body" and spec.required:
            add("blank", "   ", "missing")
        if shape.max_len:
            add("too long", "x" * (shape.max_len + 1), "malformed")
    elif isinstance(shape, Enum):
        add("out of enum", "nobody", "malformed")
    if place == "body":
        add("wrong type", _wrong_type(shape), "wrong_type")
    if place != "path" and spec.required:
        add("missing", GONE, "missing")
    if place == "body" and not spec.nullable:
        add("null", None, "missing")
    return out


def _filler(spec: Field) -> Any:
    shape = spec.shape
    if isinstance(shape, Id) and shape.minted:
        return _filler(dataclasses.replace(spec, shape=shape.of))
    if isinstance(shape, Id):
        return unknown_value(shape)
    if isinstance(shape, Str):
        return next(iter(shape.classes.values()), "x")
    if isinstance(shape, Enum):
        return shape.values[0]
    if isinstance(shape, Bool):
        return True
    if isinstance(shape, Int):
        return 1
    return None


def relation_classes(body: Object, sent: Mapping[str, Any]) -> list[InputClass]:
    out: list[InputClass] = []
    for names in body.one_ofs:
        joined = "+".join(names)
        out.append(InputClass("body", joined, "neither", None, False, "malformed", tuple((n, GONE) for n in names)))
        both = tuple((n, sent[n] if sent.get(n) is not None else _filler(body.fields[n])) for n in names)
        if all(v is not None for _, v in both):
            out.append(InputClass("body", joined, "all", None, False, "malformed", both))
    for names in body.togethers:
        if all(sent.get(n) is not None for n in names):
            for n in names:
                rest = tuple((m, GONE) for m in names if m != n)
                out.append(InputClass("body", "+".join(names), f"only {n}", None, False, "missing", rest))
    return out


def classes(call: Endpoint, model: Model, ids: Identities | None) -> list[InputClass]:
    """The classes of a call the model accepts as it stands. A call the model
    already refuses for its caller says nothing of its inputs, only of the order
    of two rules, so it has none."""
    if model.explain(call) is not None:
        return []
    cls = type(call)
    out: list[InputClass] = []
    for place, shape in zip(PLACES, (cls.params, cls.query, cls.body, cls.headers)):
        if isinstance(shape, Object):
            values = _values(call, place)
            for name, spec in shape.fields.items():
                out += field_classes(place, name, spec, model, ids, call.by, values.get(name))
        elif place == "body" and isinstance(shape, List) and isinstance(shape.of, Object):
            items = shape.pack(call.body_value)
            first = items[0] if items and isinstance(items[0], Mapping) else {}
            for name, spec in shape.of.fields.items():
                out += [dataclasses.replace(c, name=f"[].{name}")
                        for c in field_classes(place, name, spec, model, ids, call.by, first.get(name))]
    if isinstance(cls.body, Object) and (cls.body.one_ofs or cls.body.togethers):
        out += relation_classes(cls.body, cls.body.pack(call.body_value))
    if cls.typed_wire:
        out = [c for c in out if c.kind not in TYPED_AWAY]
    return out


def vary(call: Endpoint, c: InputClass) -> Endpoint:
    """The call with this one input replaced."""
    cls = type(call)

    def edited(values: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(values)
        for name, value in c.edits:
            if value is GONE:
                out.pop(name, None)
            else:
                out[name] = value
        if c.edits:
            return out
        if c.value is GONE:
            out.pop(c.name, None)
        else:
            out[c.name] = c.value
        return out

    if c.place == "path":
        target = call.of
        if isinstance(target, Fixture) and hasattr(target, c.name):
            return call.varied(of=target.but(**{c.name: c.value}))
        if isinstance(target, Mapping):
            return call.varied(of={**target, c.name: c.value})
        if isinstance(target, tuple):
            names = list(cls.params.fields)
            return call.varied(of={**dict(zip(names, target)), c.name: c.value})
        return call.varied(of={c.name: c.value})
    if c.place == "query":
        target = call.of
        if isinstance(target, Fixture) and hasattr(target, c.name) and c.value is not GONE:
            return call.varied(of=target.but(**{c.name: c.value}), query=edited(call.query_values))
        return call.varied(query=edited(call.query_values))
    if c.place == "body" and c.name.startswith("[]."):
        items = list(cast(List, cls.body).pack(call.body_value))
        if not items:
            return call
        first = dict(items[0])
        if c.value is GONE:
            first.pop(c.name[3:], None)
        else:
            first[c.name[3:]] = c.value
        return call.varied(body=[first, *items[1:]])
    if c.place == "body":
        return call.varied(body=edited(cast(Object, cls.body).pack(call.body_value)))
    return call.varied(headers=edited(call.header_values))


@dataclass
class Base:
    """A call the run saw succeed: where, and how to bring a live service and a
    fresh model to the moment just before it."""

    where: str
    arrange: Callable[[Surface, Callable[[], Model]], tuple[Model, Endpoint]]
    before: Model
    call: Endpoint


def _carried(step: object) -> TypeGuard[Endpoint]:
    return isinstance(step, Endpoint) and step.carries is not None


def _journey_base(journey: Any, k: int) -> Callable[[Surface, Callable[[], Model]], tuple[Model, Endpoint]]:
    def arrange(surface: Surface, fresh: Callable[[], Model]) -> tuple[Model, Endpoint]:
        model = fresh()
        baseline = model.rows()
        seen: dict[int, Any] = {}
        for given in journey.given:
            _ok(attempt(given, model, surface, baseline, seen))
        steps = iter(journey().steps(model.today))
        for step in itertools.islice(steps, k):
            _ok(attempt(step, model, surface, baseline, seen))
        return model, next(steps)

    return arrange


def _cell_base(scene: Any, build: Callable[[Model], object]) -> Callable[[Surface, Callable[[], Model]], tuple[Model, Endpoint]]:
    def arrange(surface: Surface, fresh: Callable[[], Model]) -> tuple[Model, Endpoint]:
        model = fresh()
        for step in scene.reached_by(model.today):
            _ok(attempt(step, model, surface))
        action = build(model)
        if not _carried(action):
            raise BookError("the cell no longer builds a call")
        return model, action

    return arrange


def _ok(step: StepResult) -> None:
    if step.skipped:
        raise CannotArrange(step.skipped)
    if not step.ok:
        raise BookError(f"the scene cannot be arranged: {step.text}: {step.note}")


def bases(service: Service[Any]) -> dict[type[Endpoint], Base]:
    """For each endpoint, the first call the journeys or the cells make that the
    model accepts, found on the model alone."""
    found: dict[type[Endpoint], Base] = {}
    for journey in service.journeys:
        model = service.new_model(date.today())
        try:
            for given in journey.given:
                model.perform(given.request)
            for k, step in enumerate(journey().steps(model.today)):
                if not _carried(step):
                    continue
                before, kept = model.copy(), copy.deepcopy(step)
                outcome = model.perform(step)
                if isinstance(outcome, Done) and type(step) not in found:
                    found[type(step)] = Base(f"journey {journey.__name__}, step {k + 1}", _journey_base(journey, k), before, kept)
        except Exception:
            continue
    for axes in service.matrices:
        for scene in axes.scenes:
            for name, build in axes.actions.items():
                try:
                    model = scene.arrange(service.new_model(axes.today))
                    action = build(model)
                    if not _carried(action) or type(action) in found:
                        continue
                    before, kept = model.copy(), copy.deepcopy(action)
                    if isinstance(model.perform(action), Done):
                        found[type(action)] = Base(f"cell {axes.record}:{scene.name} x {name}", _cell_base(scene, build), before, kept)
                except Exception:
                    continue
    return found


def refusals_for(service: Service[Any], endpoint: type[Endpoint]) -> Refusals:
    return endpoint.refusals.over(service.refusals)


def predicted(call: Endpoint, model: Model) -> Outcome | None:
    """What the model alone says of the call, or None when it cannot take it."""
    try:
        return model.copy().perform(call)
    except Exception:
        return None


def expected(c: InputClass, outcome: Outcome | None) -> bool:
    """Whether the model's own answer stands for this class: it is a valid
    class, or the model has a rule that refuses it."""
    return c.valid or isinstance(outcome, (Refusal, Flawed))


@dataclass
class Sent:
    endpoint: type[Endpoint]
    c: InputClass
    ok: bool
    note: str = ""
    outcome: str = ""
    diverged: Diverges | None = None
    known: Defect[Any, Any] | None = None
    skipped: str = ""
    clean: bool = False

    @property
    def text(self) -> str:
        return f"{self.endpoint.__name__} {self.c.label}"

    @property
    def verdict(self) -> str:
        return "SKIP" if self.skipped else "DIVERGES" if self.diverged else "PASS" if self.ok else "FAIL"


@dataclass
class Tried:
    """Every input class the run sent, in the shape the defect report reads."""

    sent: list[Sent] = field(default_factory=list)
    journey: Any = field(default_factory=lambda: SimpleNamespace(title=lambda: "the input classes"))

    @property
    def defects(self) -> list[Defect[Any, Any]]:
        return [s.known for s in self.sent if s.known is not None]

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.sent)

    @property
    def diverged(self) -> set[Diverges]:
        return {s.diverged for s in self.sent if s.diverged is not None}


def judge(service: Service[Any], call: Endpoint, c: InputClass, model: Model, surface: Surface) -> Sent:
    """Sends the varied call on the surface and the model, and compares them."""
    cls = type(call)
    said = predicted(call, model)
    if expected(c, said):
        taken = attempt(call, model, surface)
        if taken.skipped:
            raise CannotArrange(taken.skipped)
        clean = taken.ok and isinstance(taken.model, Refusal) and isinstance(taken.app, Refusal)
        return Sent(cls, c, taken.ok, taken.note, f"{taken.model} / {taken.app}", known=taken.known, clean=clean)
    want = refusals_for(service, cls).of(c.default)
    match = next((d for d in service.diverges if d.endpoint is cls and d.label == c.label), None)
    if want is None and match is None:
        return Sent(cls, c, False, f"the model has no rule for {c.label} and the book declares no {c.default} refusal")
    try:
        got = surface.perform(call)
    except (CannotArrange, Unhealthy):
        raise
    except (Undeclared, OffShape) as outside:
        return Sent(cls, c, False, f"the app answered outside the book: {outside}")
    except Exception as crash:
        return Sent(cls, c, False, f"crashed: {type(crash).__name__}: {str(crash).splitlines()[0]}")
    shown = f"{want} (the book's {c.default} refusal) / {got}" if want is not None else f"a refusal / {got}"
    if want is not None and agree(want, got) and isinstance(got, Refusal):
        if surface.rows() == listing(surface, model):
            return Sent(cls, c, True, outcome=shown, clean=True)
        return Sent(cls, c, False, "the refusal changed what is listed", shown)
    if match is not None and not isinstance(got, Refusal):
        return Sent(cls, c, True, f"declared: {match.why}", shown, diverged=match)
    return Sent(cls, c, False, f"the book expects {want or 'a refusal'}, the app said {got}", shown)


def ids_of(surface: Surface) -> Identities | None:
    client = getattr(surface, "client", None)
    return client.ids if isinstance(client, Client) else None


def play(service: Service[Any], surface: Surface, fresh: Callable[[], Model], only: frozenset[str] = frozenset()) -> Tried:
    tried = Tried()
    found = bases(service)
    skipped = {u.endpoint for u in service.unseen if u.item == "inputs"}
    for endpoint in service.endpoints:
        if only and endpoint.__name__ not in only:
            continue
        if endpoint.carries is None or not has_inputs(endpoint) or endpoint in skipped:
            continue
        base = found.get(endpoint)
        if base is None:
            continue
        count = len(classes(base.call, base.before, ids_of(surface)))
        held: tuple[Model, Endpoint] | None = None
        for n in range(count):
            sent, arranged = one(service, endpoint, base, n, surface, fresh, held)
            tried.sent.append(sent)
            held = arranged if sent.clean else None
    return tried


def one(service: Service[Any], endpoint: type[Endpoint], base: Base, n: int, surface: Surface,
        fresh: Callable[[], Model], held: tuple[Model, Endpoint] | None = None) -> tuple[Sent, tuple[Model, Endpoint] | None]:
    """Sends class `n` on the base. A world the previous class left as it found it, both sides
    having refused, is `held` and taken again instead of arranged anew."""
    try:
        model, call = held if held is not None else base.arrange(surface, fresh)
        c = classes(call, model, ids_of(surface))[n]
    except Unhealthy:
        raise
    except CannotArrange as cannot:
        return Sent(endpoint, InputClass("", f"class {n + 1}", "", None, False), True, skipped=cannot.reason), None
    except Exception as crash:
        label = f"class {n + 1}"
        c = InputClass("", label, "", None, False)
        return Sent(endpoint, c, False, f"the base ({base.where}) cannot be arranged: {type(crash).__name__}: {crash}"), None
    try:
        return judge(service, vary(call, c), c, model, surface), (model, call)
    except CannotArrange as cannot:
        return Sent(endpoint, c, True, skipped=cannot.reason), None
    except BookError as wrong:
        return Sent(endpoint, c, False, f"the book contradicts itself: {wrong}"), None
