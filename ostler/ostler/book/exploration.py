"""Typed exploration: a breadth-first walk over the model's own state graph,
then every state, action and input class the walk reached, played once on the
app. The model tells the states apart, so the app pays once per distinct cell
and never for a sequence the model already folded.

Two models with one signature are one state. A signature is, per
matrix, the scene each entity of the record is in, counted none, one or many.
Each state is kept with the shortest path of calls that reached it. A path is
the position of each call among the calls its model offers, so it replays on a
fresh model whose ids differ."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, cast

from ostler.book.arrange import Arrange
from ostler.book.backstage import CannotArrange
from ostler.book.domain import Change, State, Transaction
from ostler.book.errors import BookError
from ostler.book.explore import _overrides, moves
from ostler.book.http import Endpoint
from ostler.book.inputs import InputClass, classes, expected, ids_of, judge, vary
from ostler.book.model import Flaw, Model, Refused, Rule
from ostler.book.outcome import Done, Outcome
from ostler.book.runner import attempt
from ostler.book.service import Service
from ostler.book.state import Impossible
from ostler.book.surface import Surface

BASELINE = "baseline"
REFUSED = "refused:"


def signature(service: Service[Any], model: Model) -> str:
    parts: list[str] = []
    for axes in service.matrices:
        counted = Counter(axes.marks(model))
        told = ", ".join(f"{name} {'many' if n > 1 else 'one'}" for name, n in sorted(counted.items()))
        parts.append(f"{axes.record} {told or 'none'}")
    return " | ".join(parts)


def outside_moves(service: Service[Any], model: Model) -> list[Arrange[Any]]:
    """Every outside event of the service aimed at each example its fixture
    gives for this state. An outside event has no caller."""
    found: list[Arrange[Any]] = []
    for event in service.outside:
        accept = event.carries.accept if event.carries is not None else None
        if not _overrides(accept):
            continue
        seen: set[str] = set()
        for by in (None, *service.cast):
            for example in accept.examples(model, by):
                move = event(example)
                if code(move) not in seen:
                    seen.add(code(move))
                    found.append(move)
    return found


def calls(service: Service[Any], model: Model) -> list[Any]:
    """The valid calls from a state, then the outside events the state can take.
    A service with endpoints derives the calls from the shapes; one with
    interactions only has the acts its matrices build."""
    return [*own_calls(service, model), *outside_moves(service, model)]


def own_calls(service: Service[Any], model: Model) -> list[Any]:
    if service.endpoints:
        return list(moves(service.endpoints, cast=service.cast)(model))
    found: list[Any] = []
    seen: set[tuple[Any, ...]] = set()
    for axes in service.matrices:
        for build in axes.actions.values():
            try:
                call = cast(Any, build(model))
            except Exception:
                continue
            if call is None or isinstance(call, Impossible) or getattr(call, "carries", None) is None:
                continue
            key = (type(call), call.by, tuple(sorted(vars(call.of).items(), key=lambda item: item[0])) if call.of is not None else ())
            if key not in seen:
                seen.add(key)
                found.append(call)
    return found


def code(call: Any) -> str:
    replay = getattr(call, "replay", None)
    if callable(replay):
        return cast(str, replay())
    given = ", ".join(f"{k}={v!r}" for k, v in vars(call.of).items() if v is not None) if call.of is not None else ""
    return f"{type(call).__name__}({type(call.of).__name__ + '(' + given + ')' if given else ''})"


@dataclass
class Node:
    """One distinct state: its signature, how deep it first appeared, the
    positions of the calls that reached it, and a model standing there."""

    signature: str
    depth: int
    path: tuple[int, ...]
    model: Model


@dataclass
class Walk:
    nodes: list[Node] = field(default_factory=list)
    per_depth: list[int] = field(default_factory=list)
    reached: int = 0
    stopped: str = ""
    wide: list[str] = field(default_factory=list)


def walk(service: Service[Any], start: Model, depth: int) -> Walk:
    """Breadth-first over the calls the model accepts, states deduped by
    signature, stopping at the depth bound or at the first depth that adds no
    new signature."""
    first = Node(signature(service, start), 0, (), start)
    found = Walk([first], [1])
    known = {first.signature}
    frontier = [first]
    while True:
        if found.reached >= depth:
            found.stopped = f"the depth bound {depth}"
            return found
        fresh: list[Node] = []
        for node in frontier:
            for position, call in enumerate(calls(service, node.model)):
                after = node.model.copy()
                try:
                    after.apply(call)
                except (Refused, Flaw):
                    continue
                sig = signature(service, after)
                if sig in known:
                    continue
                known.add(sig)
                fresh.append(Node(sig, found.reached + 1, node.path + (position,), after))
        if not fresh:
            found.stopped = f"depth {found.reached + 1} added no new signature"
            return found
        found.reached += 1
        found.per_depth.append(len(fresh))
        found.nodes += fresh
        frontier = fresh


@dataclass(frozen=True)
class Cell:
    """One thing to play: in a state, an action by an actor with one input
    class. Its key is (scope, endpoint, actor handle, class label), where the
    scope is the signature cut to the records whose matrices name the endpoint."""

    node: Node = field(compare=False)
    endpoint: str
    actor: str
    label: str
    position: int = field(compare=False)
    writes: bool = field(compare=False)
    scope: str = ""

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.scope or self.node.signature, self.endpoint, self.actor, self.label)

    @property
    def text(self) -> str:
        return f"{self.endpoint} by {self.actor}, {self.label}, at {self.scope or self.node.signature}"

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Cell) and self.key == other.key


def effect(model: Model, call: Any) -> tuple[Outcome | None, bool]:
    """What the model alone answers the call, and whether it changed anything."""
    twin = model.copy()
    try:
        outcome = twin.perform(call)
    except Exception:
        return None, False
    if not isinstance(outcome, Done):
        return outcome, False
    log = getattr(twin, "log", None)
    reduced = log[-1].result if log else None
    return outcome, isinstance(reduced, Change) or (isinstance(reduced, Transaction) and bool(reduced.changes))


def cells_at(service: Service[Any], node: Node, classed: set[tuple[str, str]] | None = None,
             refused: set[tuple[str, str, str]] | None = None) -> list[Cell]:
    """For each action and actor whose baseline call the model accepts here, the
    baseline, and one cell per input class the shapes derive unless that
    endpoint and actor already had their classes at an earlier state. An input
    class describes the input, not the state."""
    classed = set() if classed is None else classed
    refused = set() if refused is None else refused
    offered = calls(service, node.model)
    found: list[Cell] = []
    met: set[tuple[type, object]] = set()
    for position, call in enumerate(offered):
        if isinstance(call, Arrange):
            continue
        kind = (type(call), call.by)
        why = node.model.explain(call)
        if isinstance(why, Rule):
            actor = call.by.handle if call.by is not None else "nobody"
            mark = (why.name, type(call).__name__, actor)
            if mark not in refused:
                refused.add(mark)
                found.append(Cell(node, type(call).__name__, actor, f"{REFUSED}{why.name}", position, False))
            continue
        if kind in met or why is not None:
            continue
        met.add(kind)
        actor = call.by.handle if call.by is not None else "nobody"
        _, writes = effect(node.model, call)
        found.append(Cell(node, type(call).__name__, actor, BASELINE, position, writes))
        if isinstance(call, Endpoint) and (type(call).__name__, actor) not in classed:
            classed.add((type(call).__name__, actor))
            for c in classes(call, node.model, None):
                found.append(Cell(node, type(call).__name__, actor, c.label, position, class_writes(node.model, call, c)))
    return found


def class_writes(model: Model, call: Endpoint, c: InputClass) -> bool:
    try:
        outcome, changed = effect(model, vary(call, c))
    except BookError:
        return False
    return changed and expected(c, outcome)


def footprints(service: Service[Any], nodes: list[Node]) -> dict[str, set[int]]:
    """For each endpoint, the matrices whose actions build a call to it. A
    matrix that names an endpoint is a record the endpoint reads or writes."""
    found: dict[str, set[int]] = {}
    for index, axes in enumerate(service.matrices):
        for build in axes.actions.values():
            for node in nodes:
                try:
                    call = build(node.model.copy())
                except Exception:
                    continue
                if call is not None and not isinstance(call, Impossible):
                    found.setdefault(type(call).__name__, set()).add(index)
                    break
    return found


def scoped(signature: str, footprint: set[int] | None) -> str:
    if not footprint:
        return signature
    parts = signature.split(" | ")
    return " | ".join(parts[i] for i in sorted(footprint))


def answer(cell: Cell, offered: list[Any]) -> str:
    if cell.label != BASELINE:
        return ""
    outcome, writes = effect(cell.node.model, offered[cell.position])
    return f"{type(outcome).__name__} {getattr(outcome, 'status', '')} {writes}"


def seed(service: Service[Any], start: Model, depth: int) -> tuple[Walk, list[Cell]]:
    """Every cell the walk reaches, one per scope. An endpoint whose model
    answer differs between two states of one scope reads a record its
    matrices do not name, so it keeps the whole signature."""
    walked = walk(service, start, depth)
    reach = footprints(service, walked.nodes)
    classed: set[tuple[str, str]] = set()
    refused: set[tuple[str, str, str]] = set()
    every = [cell for node in walked.nodes for cell in cells_at(service, node, classed, refused)]
    told: dict[tuple[str, str, str, str], str] = {}
    wide: set[str] = set()
    offered: dict[str, list[Any]] = {}
    for cell in every:
        key = (scoped(cell.node.signature, reach.get(cell.endpoint)), cell.endpoint, cell.actor, cell.label)
        if cell.label == BASELINE and cell.node.signature not in offered:
            offered[cell.node.signature] = calls(service, cell.node.model)
        said = answer(cell, offered.get(cell.node.signature, []))
        if told.setdefault(key, said) != said:
            wide.add(cell.endpoint)
    found: dict[Cell, None] = {}
    for cell in every:
        scope = cell.node.signature if cell.endpoint in wide else scoped(cell.node.signature, reach.get(cell.endpoint))
        found.setdefault(Cell(cell.node, cell.endpoint, cell.actor, cell.label, cell.position, cell.writes, scope))
    walked.wide = sorted(wide)
    return walked, list(found)


def declared_rules(service: Service[Any], model: Model) -> list[str]:
    names: dict[str, None] = {}
    for endpoint in service.endpoints:
        if endpoint.carries is not None:
            for rule in endpoint.carries.rules:
                names[rule.name] = None
    roots: list[type[State]] = [c for c in type(model).__mro__ if issubclass(c, State) and c is not State]
    for root in roots[-1:]:
        for kind in (root, *states_below(root)):
            for rule in kind.rules:
                names[rule.name] = None
    return list(names)


def states_below(kind: type[State]) -> list[type[State]]:
    found: list[type[State]] = []
    for sub in kind.__subclasses__():
        found += [sub, *states_below(sub)]
    return found


def never_refused(service: Service[Any], model: Model, cells: list[Cell]) -> list[str]:
    met = {c.label[len(REFUSED):] for c in cells if c.label.startswith(REFUSED)}
    return [name for name in declared_rules(service, model) if name not in met]


def unreached(service: Service[Any], today: date, walked: Walk) -> list[str]:
    """The scenes the state table declares whose signature the walk never met."""
    known = {n.signature for n in walked.nodes}
    missing: list[str] = []
    for axes in service.matrices:
        for scene in axes.scenes:
            try:
                sig = signature(service, scene.arrange(service.new_model(today)))
            except Exception as crash:
                missing.append(f"{axes.record}:{scene.name} cannot be arranged: {type(crash).__name__}: {crash}")
                continue
            if sig not in known:
                missing.append(f"{axes.record}:{scene.name}  {sig}")
    return missing


@dataclass
class Failure:
    text: str
    path: list[str]
    note: str


@dataclass
class Played:
    played: int = 0
    arrangements: int = 0
    shared: int = 0
    shared_cells: int = 0
    failures: list[Failure] = field(default_factory=list)
    skips: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures


class Arranged:
    """A fresh model and a live surface taken along one state's path."""

    def __init__(self, model: Model | None, listing: list[Any], path: list[str], note: str, skipped: str = ""):
        self.model, self.listing, self.path, self.note, self.skipped = model, listing, path, note, skipped
        self.served = 0


def arrange(service: Service[Any], node: Node, surface: Surface, fresh: Callable[[], Model]) -> Arranged:
    try:
        model = fresh()
    except CannotArrange as cannot:
        return Arranged(None, [], [], "", cannot.reason)
    path: list[str] = []
    for position in node.path:
        offered = calls(service, model)
        if position >= len(offered):
            return Arranged(None, [], path, f"the path no longer offers call {position + 1}")
        call = offered[position]
        path.append(code(call))
        step = attempt(call, model, surface)
        if step.skipped:
            return Arranged(None, [], path, "", step.skipped)
        if not step.ok:
            return Arranged(None, [], path, f"{step.text}: {step.note}")
    return Arranged(model, calls(service, model), path, "")


def take(service: Service[Any], cell: Cell, arranged: Arranged, surface: Surface) -> tuple[bool, str, bool]:
    """Plays the cell on an arranged state: whether it passed, what to say, and
    whether the app took something the book refuses."""
    assert arranged.model is not None
    if cell.position >= len(arranged.listing) or type(arranged.listing[cell.position]).__name__ != cell.endpoint:
        return False, "the state no longer offers this call", False
    call = arranged.listing[cell.position]
    if cell.label == BASELINE or cell.label.startswith(REFUSED):
        taken = attempt(call, arranged.model, surface)
        if taken.skipped:
            raise CannotArrange(taken.skipped)
        return taken.ok, taken.note, False
    c = next((x for x in classes(call, arranged.model, ids_of(surface)) if x.label == cell.label), None)
    if c is None:
        return False, f"the class {cell.label} no longer derives", False
    try:
        sent = judge(service, vary(call, c), c, arranged.model, surface)
    except BookError as wrong:
        return False, f"the book contradicts itself: {wrong}", False
    return sent.ok, sent.note, sent.diverged is not None


def retire(done: Played, arranged: Arranged | None) -> None:
    if arranged is not None and arranged.served > 1:
        done.shared += 1
        done.shared_cells += arranged.served


def play(service: Service[Any], cells: list[Cell], surface: Surface, fresh: Callable[[], Model]) -> Played:
    """Each cell is arranged from a fresh model by replaying its state's path.
    The cells of one state that change nothing share one arrangement and are
    taken first, because an arrangement resets the one surface; each accepted
    write then gets its own."""
    done = Played()
    by_node: dict[str, list[Cell]] = {}
    for cell in cells:
        by_node.setdefault(cell.node.signature, []).append(cell)
    for group in by_node.values():
        node = group[0].node
        group.sort(key=lambda cell: cell.writes)
        shared: Arranged | None = None
        for n, cell in enumerate(group):
            if cell.writes or shared is None:
                arranged = arrange(service, node, surface, fresh)
                done.arrangements += 1
                if arranged.model is None and arranged.skipped:
                    done.skips += [arranged.skipped] * (len(group) - n)
                    break
                if arranged.model is None:
                    done.failures.append(Failure(f"state {node.signature}", arranged.path,
                                                 f"{len(group) - n} cells not played: {arranged.note}"))
                    break
                if not cell.writes:
                    shared = arranged
            else:
                arranged = shared
            arranged.served += 1
            try:
                ok, note, diverged = take(service, cell, arranged, surface)
            except CannotArrange as cannot:
                done.skips.append(cannot.reason)
                if not cell.writes:
                    retire(done, shared)
                    shared = None
                continue
            done.played += 1
            if not ok:
                done.failures.append(Failure(cell.text, [*arranged.path, f"{cell.endpoint} ({cell.label})"], note))
            if not cell.writes and (not ok or diverged):
                retire(done, shared)
                shared = None
        retire(done, shared)
    return done
