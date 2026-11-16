"""Walks a journey on the model and on the surface, step by step, and records
whether the app did what the model says it does, and what the model reduced
each step to."""

from __future__ import annotations

import atexit
import dataclasses
import signal
from dataclasses import replace
from typing import Any, Callable, Iterable, cast

from ostler.book.arrange import Arrange
from ostler.book.asked import Asked, Unasked
from ostler.book.backstage import CannotArrange
from ostler.book.boundary import Needs
from ostler.book.cast import SOLE, Actor
from ostler.book.delivery import Delivery, faults as detail_faults
from ostler.book.domain import Action, State
from ostler.book.event import Event
from ostler.book.entries import says
from ostler.book.errors import BookError, Unhealthy
from ostler.book.http import Client, Endpoint, Id, Identities, List, Object, OffShape, Shape, Undeclared, canonical
from ostler.book.journey import (Check, Given, Journey, JourneyResult, Listed, OwnerRefused, Refused, Relates, Same, Seen, Shows,
                                 StepResult, Undo, difference, masked)
from ostler.book.model import Defect, Model
from ostler.book.owners import Owners
from ostler.book.outcome import CannotReach, Done, Flawed, Outcome, Refusal, Unreachable
from ostler.book.status import refused as turned_away
from ostler.book.surface import Surface


RETAKES = 1000
PATIENCE = 50
REREADS = 3


def agree(model: Outcome, app: Outcome) -> bool:
    if isinstance(app, Unreachable):
        return isinstance(model, Refusal)
    if isinstance(model, Refusal):
        return (isinstance(app, Refusal) and model.message == app.message
                and (app.status == 0 or model.status == app.status))
    return isinstance(app, Done)


def walk(journey: type[Journey], model: Model, surface: Surface) -> JourneyResult:
    """Takes the journey on a model and a surface already in step, whatever the
    journeys before it left behind."""
    result = JourneyResult(journey, surface.name)
    baseline = model.rows()
    seen: dict[int, Seen] = {}
    cover(surface, None, [], model)
    Owners.journey()
    for given in journey.given:
        result.steps.append(attempt(given, model, surface, baseline, seen))
        if result.steps[-1].skipped:
            break
    try:
        if result.ok and not result.skipped:
            for step in journey().steps(model.today):
                result.steps.append(attempt(step, model, surface, baseline, seen))
                if not result.steps[-1].ok or result.steps[-1].skipped:
                    break
    finally:
        if not result.skipped:
            for given in reversed(journey.given):
                if isinstance(given, Given) and given.undo is not None:
                    attempt(Undo(given), model, surface, baseline)
    result.state = model.describe()
    return result


def attempt(step: object, model: Model, surface: Surface, baseline: tuple[object, ...] = (),
            seen: dict[int, Seen] | None = None) -> StepResult:
    """Takes one step on both sides and turns anything that escapes into a failed step.
    The step's text is read before it is taken: a fixture moves on with later steps."""
    text = str(step)
    at = offset(surface)
    try:
        result = take(step, model, surface, baseline, seen if seen is not None else {})
    except Unhealthy:
        raise
    except CannotArrange as cannot:
        result = StepResult(step, None, None, model.rows(), (), True, f"skipped: {cannot.reason}", skipped=cannot.reason)
    except (Undeclared, OffShape) as outside:
        result = StepResult(step, None, None, model.rows(), (), False, f"the app answered outside the book: {outside}")
    except BookError as wrong:
        result = StepResult(step, None, None, model.rows(), (), False, f"the book contradicts itself: {wrong}")
    except Exception as crash:
        result = StepResult(step, None, None, model.rows(), (), False, f"crashed: {type(crash).__name__}: {str(crash).splitlines()[0]}")
    cover(surface, None, [], model)
    result.text = text
    result.at = at
    stray = strays(surface)
    if stray and not result.skipped:
        note = "the page sent a request no screen declares: " + ", ".join(stray)
        result.note = f"{result.note}; {note}" if result.note else note
        result.ok = False
    faults = list_faults(surface)
    if faults and not result.skipped:
        note = "; ".join(faults)
        result.note = f"{result.note}; {note}" if result.note else note
        result.ok = False
    return result


def offset(surface: Surface) -> float | None:
    ask = getattr(surface, "offset", None)
    return cast(Callable[[], float | None], ask)() if callable(ask) else None


def strays(surface: Surface) -> list[str]:
    ask = getattr(surface, "strays", None)
    return list(cast(Callable[[], Iterable[str]], ask)()) if callable(ask) else []


def list_faults(surface: Surface) -> list[str]:
    ask = getattr(surface, "list_faults", None)
    return list(cast(Callable[[], Iterable[str]], ask)()) if callable(ask) else []


def blocked(journey: type[Journey], surface: Surface, reason: str) -> JourneyResult:
    result = JourneyResult(journey, surface.name)
    result.steps.append(StepResult("arrange", None, None, (), (), True, f"skipped: {reason}", text="arrange", skipped=reason))
    return result


def trace(model: Model) -> str:
    log = getattr(model, "log", None)
    return str(log[-1].result) if log else ""


def shown(surface: Surface, rows: tuple[object, ...]) -> tuple[object, ...]:
    convert = getattr(surface, "shown", None)
    return tuple(convert(row) for row in rows) if convert is not None else rows


def listing(surface: Surface, model: Model) -> tuple[object, ...]:
    """What the model says the surface lists now."""
    watched = getattr(surface, "watched", None)
    return cast(Callable[[Model], tuple[object, ...]], watched)(model) if callable(watched) else shown(surface, model.rows())


def take(step: object, model: Model, surface: Surface, baseline: tuple[object, ...],
         seen: dict[int, Seen]) -> StepResult:
    if isinstance(step, (Same, Relates, Shows)):
        return relation(step, model, seen)
    if isinstance(step, Refused):
        return refused(step, model, surface)
    if isinstance(step, OwnerRefused):
        return owner_refused(step, model, surface)
    if isinstance(step, Check):
        probed = step.probe(surface)
        return StepResult(step, None, None, model.rows(), (), probed is None, probed or "")
    if isinstance(step, Undo):
        return perform(step, step.given.undo, model, surface)
    if isinstance(step, Given):
        return perform(step, step.request, model, surface)
    if isinstance(step, Needs):
        return Owners.arrange(step, model, attempt)
    if isinstance(step, Listed):
        return listed(step, model, surface, baseline)
    if getattr(step, "carries", True) is None:
        return read(step, model, surface, seen)
    result = perform(step, step, model, surface)
    remember(step, surface, result.app_rows, seen)
    return result


def remember(step: object, surface: Surface, rows: tuple[object, ...], seen: dict[int, Seen]) -> None:
    reply = getattr(step, "reply", None)
    seen[id(step)] = Seen(rows, getattr(reply, "body", None))


def read(step: object, model: Model, surface: Surface, seen: dict[int, Seen]) -> StepResult:
    """A read the model does not compute: the surface alone answers, and only a refusal fails it."""
    if getattr(type(step), "reaches", None) is not None:
        Owners.prepare(cast(Endpoint, step))
    clear_breaches(surface)
    owed = owed_by(model, step)
    cover(surface, step, owed, model)
    try:
        outcome = surface.perform(step)
    except CannotReach as blocked:
        outcome = Unreachable(blocked.reason)
    ok = isinstance(outcome, Done)
    rows = outcome.rows if isinstance(outcome, Done) else ()
    remember(step, surface, rows, seen)
    note = "" if ok else f"app said {outcome}"
    if ok and getattr(type(step), "passes", None) is not None:
        note = Owners.judge(cast(Endpoint, step))
        ok = not note
    if ok and getattr(type(step), "reaches", None) is not None:
        note = Owners.reach(cast(Endpoint, step), listing)
        ok = not note
    ok, note, known = settle(ok, note, *judged(step, owed, model, surface))
    return StepResult(step, None, outcome, model.rows(), rows, ok, note, known=known)


def refused(step: Refused, model: Model, surface: Surface) -> StepResult:
    """A refusal claimed on a read the model does not carry: only the surface answers."""
    inner = step.step
    if not hasattr(inner, "carries") or getattr(inner, "carries") is not None:
        raise BookError(f"{inner} is carried by the model: write a rule for its refusal, not a Refused claim")
    try:
        outcome = surface.perform(inner)
    except CannotReach as blocked:
        outcome = Unreachable(blocked.reason)
    ok = (isinstance(outcome, Refusal) and outcome.status == step.status
          and (step.message is None or outcome.message == step.message))
    claimed = f"{step.status}" + (f" {step.message}" if step.message else "")
    return StepResult(step, None, outcome, model.rows(), (), ok, "" if ok else f"claimed {claimed}, app said {outcome}")


def owner_refused(step: OwnerRefused, model: Model, surface: Surface) -> StepResult:
    """A refusal of the owner claimed to come back as the book maps it: the step goes to the neighbour, the owner's
    call goes to the owner as the same actor, and the two answers are judged against the map."""
    inner = step.step
    kind = type(inner)
    if getattr(kind, "passes", None) is None and getattr(kind, "reaches", None) is None:
        raise BookError(f"{kind.__name__} passes nothing on and reaches nothing: claim its own refusals with Refused")
    try:
        outcome: Outcome = surface.perform(inner)
        reply = getattr(inner, "reply", None)
        app = reply.status if reply is not None else 0
    except CannotReach as blocked:
        return StepResult(step, None, Unreachable(blocked.reason), model.rows(), (), False, f"the surface never offers this: {blocked.reason}")
    except Undeclared as outside:
        outcome, app = Refusal(str(outside), outside.status), outside.status
    note = Owners.refused(cast(Endpoint, inner), app)
    return StepResult(step, None, outcome, model.rows(), (), not note, note)


def recorded(step: object, seen: dict[int, Seen]) -> Seen:
    if id(step) not in seen:
        raise BookError(f"{step} was not taken before this relation")
    return seen[id(step)]


def side(found: Seen, other: Seen) -> object:
    return found.body if found.body is not None and other.body is not None else list(found.rows)


def relation(step: Same | Relates | Shows, model: Model, seen: dict[int, Seen]) -> StepResult:
    if isinstance(step, Same):
        first, second = recorded(step.first, seen), recorded(step.second, seen)
        left, right = side(first, second), side(second, first)
        note = difference(masked(left, *step.but), masked(right, *step.but)) or ""
    elif isinstance(step, Shows):
        got = recorded(step.step, seen)
        note = difference(list(got.rows), list(step.rows)) or ""
    else:
        note = step.holds(*(recorded(s, seen) for s in step.steps)) or ""
    return StepResult(step, None, None, model.rows(), (), not note, note)


def without(rows: tuple[object, ...], baseline: tuple[object, ...]) -> tuple[object, ...]:
    """The rows left once the first occurrence of each baseline row is taken out."""
    owed = list(baseline)
    kept = []
    for row in rows:
        if row in owed:
            owed.remove(row)
        else:
            kept.append(row)
    return tuple(kept)


def listed(step: Listed, model: Model, surface: Surface, baseline: tuple[object, ...]) -> StepResult:
    began = shown(surface, baseline)
    kept = []
    for fixture in step.of:
        entity = model.lookup(fixture)
        if entity is None:
            raise BookError(f"the model keeps nothing for {fixture}")
        kept.append(model.row(entity))
    expected = shown(surface, tuple(kept))
    rows = without(surface.rows(), began)
    ok = rows == expected
    note = "" if ok else "listed " + str([str(r) for r in rows]) + " where the author expects " + str([str(r) for r in expected])
    modelled = without(shown(surface, model.rows()), began)
    if ok and modelled != expected:
        ok, note = False, "the model lists " + str([str(r) for r in modelled]) + ", not what the author expects"
    return StepResult(step, None, None, model.rows(), rows, ok, note)


def expectations(request: object, model: Model) -> dict[str, tuple[Any, ...]]:
    """For each list of the request's screen that states who belongs, who never does or a picked entry given by a
    function, what the model says before the step moves it, for the person taking the step."""
    screen = getattr(type(request), "screen", None)
    if screen is None:
        return {}
    by = getattr(request, "by", None)
    wanted: dict[str, tuple[Any, ...]] = {}
    for attribute, component in screen.attributes():
        lists = component.lists
        chosen = lists.picked if lists is not None and callable(lists.picked) else None
        if lists is None or (lists.always is None and lists.never is None and chosen is None):
            continue
        where = f"{screen.__name__}.{attribute}"
        try:
            belong = list(lists.always(model, by)) if lists.always is not None else []
            never = list(lists.never(model, by)) if lists.never is not None else []
            picked = [chosen(model, by)] if chosen is not None else []
        except Exception as crash:
            raise BookError(f"the list {where} cannot say who belongs: {type(crash).__name__}: {crash}") from None
        wanted[where] = (belong, never, *picked)
    return wanted


def asked_feeds(request: object) -> dict[str, Any]:
    """For each list of the request's screen filled from a backend's call, the answer that call gets from the backend
    through its book, as the person taking the step, or why it got none."""
    screen = getattr(type(request), "screen", None)
    if screen is None:
        return {}
    by = getattr(request, "by", SOLE)
    fed: dict[str, Any] = {}
    for attribute, component in screen.attributes():
        lists = component.lists
        if lists is not None and isinstance(lists.given, Asked):
            fed[f"{screen.__name__}.{attribute}"] = ask_backend(lists.given, by)
    return fed


def ask_backend(given: Asked, by: object) -> Any:
    try:
        call = given.call()
    except (BookError, TypeError) as cannot:
        return Unasked(f"the call cannot be built with no input: {cannot}")
    call.by = cast(Actor | None, by)
    try:
        owner, _, surface = Owners.asked(call)
        reply = Owners.sender(owner, surface, "a list fed by its call")(call)
    except BookError as wrong:
        return Unasked(str(wrong))
    if reply.refusal is not None:
        return Unasked(f"the owner {owner} refused {call}: {reply.refusal}")
    return reply.body


def hand_over(surface: Surface, wanted: dict[str, tuple[Any, ...]], asked: dict[str, Any] | None = None) -> None:
    ask = getattr(surface, "expecting", None)
    if callable(ask):
        ask(wanted, asked) if asked else ask(wanted)


def perform(step: object, request: object, model: Model, surface: Surface) -> StepResult:
    wanted = expectations(request, model)
    fed = asked_feeds(request)
    if wanted or fed:
        hand_over(surface, wanted, fed)
    try:
        return move(step, request, model, surface)
    finally:
        if wanted or fed:
            hand_over(surface, {})


def delivered(request: object) -> Arrange[Any] | None:
    """The hearing this request is, when the environment names a way to place its event and the hearing builds the detail."""
    if Deliveries.role is not None and isinstance(request, Arrange) and request.delivers():
        return request
    return None


def occurrence(hearing: Arrange[Any], model: Model) -> tuple[dict[str, Any], str]:
    """The detail of one occurrence of a hearing, and what it gets wrong against the contract of its event."""
    detail = hearing.detail(model)
    assert hearing.heard is not None
    wrong = detail_faults(hearing.heard, detail, hearing.reads)
    note = f"the detail of {type(hearing).__name__} is off the contract of event {hearing.heard.name}: " + "; ".join(wrong) if wrong else ""
    return cast(dict[str, Any], detail), note


def owed_by(model: object, call: object) -> list[Defect[Any, Any]]:
    breaking = getattr(model, "breaking", None)
    return list(cast("Iterable[Defect[Any, Any]]", breaking(call))) if callable(breaking) else []


def clear_breaches(surface: Surface) -> None:
    take = getattr(surface, "take_breaches", None)
    if callable(take):
        take()


def cover(surface: Surface, request: object | None, owed: list[Defect[Any, Any]], model: Model) -> None:
    """Tells the surface which entries of an answer belong to a known defect: those that break, alone, the rule a defect
    covers for the call, by the same reading `judged` makes. Between steps, a read is covered by the model as it stands."""
    hook = getattr(surface, "cover", None)
    if not callable(hook):
        return
    hook(lambda call: tuple(d.breaks for d in (owed if request is not None and call is request else owed_by(model, call))
                            if d.breaks is not None))


def judged(request: object, owed: list[Defect[Any, Any]], model: Model, surface: Surface) -> tuple[list[str], Defect[Any, Any] | None]:
    """What the entry rules say of every list the surface read since the step began: a note for each rule broken that no
    known defect covers, and the first known defect that covers one. A defect covers the rule for the call whose action
    declares it, when it shows for that call: the step's own call by the state before the step, a watch read by the
    state after it."""
    take = cast("Callable[[], list[Any]] | None", getattr(surface, "take_breaches", None))
    if not callable(take):
        return [], None
    notes: list[str] = []
    known: Defect[Any, Any] | None = None
    for breach in take():
        covers = owed if breach.call is request else owed_by(model, breach.call)
        defect = next((d for d in covers if d.breaks is breach.rule), None)
        if defect is None:
            notes.append(f"{type(breach.call).__name__} answers a list that breaks {says(breach.rule)} at {breach.path}: {breach.said}")
        elif known is None:
            known = defect
    return notes, known


def settle(ok: bool, note: str, notes: list[str], known: Defect[Any, Any] | None) -> tuple[bool, str, Defect[Any, Any] | None]:
    if notes:
        return False, "; ".join(part for part in (note, *notes) if part), None
    if known is not None and ok:
        return ok, note or f"known defect: breaks {says(cast(Any, known.breaks))}: {known.message}", known
    return ok, note, None


def move(step: object, request: object, model: Model, surface: Surface) -> StepResult:
    clear_breaches(surface)
    owed = owed_by(model, request)
    cover(surface, request, owed, model)
    hearing = delivered(request)
    action = emitter(request)
    if action is not None:
        Deliveries.watch()
    detail: dict[str, Any] = {}
    if hearing is not None:
        detail, wrong = occurrence(hearing, model)
        if wrong:
            return StepResult(step, None, None, model.rows(), (), False, wrong)
    model_outcome = spoken(surface, model.perform(request))
    reduced = trace(model)
    try:
        if hearing is not None and Deliveries.role is not None and hearing.heard is not None:
            Deliveries.role.place(hearing.heard, detail)
            app_outcome: Outcome = Done()
        elif action is not None and action.clock and isinstance(request, Arrange):
            app_outcome = Done()
        else:
            app_outcome = surface.perform(request)
    except CannotReach as blocked:
        app_outcome = Unreachable(blocked.reason)
    if isinstance(model_outcome, Flawed):
        return flawed(step, model_outcome, app_outcome, model, surface, reduced)
    express = getattr(surface, "express", None)
    answered = ""
    model_rows = listing(surface, model)
    if isinstance(request, Arrange) and isinstance(app_outcome, Done):
        app_rows, reads = landed(surface, model_rows)
    else:
        app_rows, reads = surface.rows(), 1
    if callable(express) and hearing is None and isinstance(model_outcome, Done) and isinstance(app_outcome, Done):
        answered = difference(express(request, model_outcome), app_outcome.view) or ""
    ok = agree(model_outcome, app_outcome) and model_rows == app_rows and not answered
    note = ""
    if not agree(model_outcome, app_outcome):
        note = f"model said {model_outcome}, app said {app_outcome}"
    elif answered:
        note = f"the answer differs: {answered}"
    elif model_rows != app_rows:
        note = "rows differ: model " + str([str(r) for r in model_rows]) + " app " + str([str(r) for r in app_rows])
        if reads > 1:
            note += f"; the event had not landed after {reads} reads"
    elif isinstance(app_outcome, Unreachable):
        note = f"the surface never offers this: {app_outcome.reason}"
    if hearing is not None and ok:
        ok, note, model_rows, app_rows = repeated(hearing, detail, request, model, surface, model_rows, reads)
    if action is not None and ok and isinstance(app_outcome, Done):
        note = emissions(action, request, model, surface)
        ok = not note
    ok, note, known = settle(ok, note, *judged(request, owed, model, surface))
    return StepResult(step, model_outcome, app_outcome, model_rows, app_rows, ok, note, reduced, known=known)


def repeated(hearing: Arrange[Any], detail: dict[str, Any], request: object, model: Model, surface: Surface,
             held: tuple[object, ...], reads: int) -> tuple[bool, str, tuple[object, ...], tuple[object, ...]]:
    """The same event placed again after it landed. By default the service ends where it was, so the watch is read as
    many times as the first landing took, and at least `REREADS`, and every reading must show the rows the model had.
    A hearing that declares it applies again has the model perform the action a second time and lands as the first did."""
    assert Deliveries.role is not None and hearing.heard is not None
    Deliveries.role.place(hearing.heard, detail)
    Deliveries.delivered += 1
    if hearing.repeat is None:
        for _ in range(max(reads, REREADS)):
            got = surface.rows()
            if got != held:
                Deliveries.failed += 1
                return (False, "the second delivery was applied again: rows model " + str([str(r) for r in held])
                        + " app " + str([str(r) for r in got]), held, got)
        return True, "", held, held
    outcome = model.perform(request)
    if not isinstance(outcome, Done):
        Deliveries.failed += 1
        return False, f"the model said {outcome} to the second delivery", held, held
    wanted = listing(surface, model)
    got, took = landed(surface, wanted)
    if got != wanted:
        Deliveries.failed += 1
        note = ("rows differ after the second delivery, which the hearing declares applies again: model "
                + str([str(r) for r in wanted]) + " app " + str([str(r) for r in got]))
        return False, note + (f"; the event had not landed after {took} reads" if took > 1 else ""), wanted, got
    Deliveries.declared += 1
    return True, "", wanted, got


def emitter(request: object) -> type[Action[Any, Any]] | None:
    """The action this request carries, when it emits an event."""
    action = getattr(type(request), "carries", None)
    return action if isinstance(action, type) and issubclass(action, Action) and action.emits else None


class Held(Identities):
    """The registry of a surface that issues no ids: an id is the run's when the model keeps a record that holds it."""

    def __init__(self, model: Model) -> None:
        super().__init__()
        self.model = model

    def model_of(self, kind: type, real: str) -> str | None:
        if not isinstance(self.model, State):
            return None
        for name in self.model.collections():
            for entity in getattr(self.model, name):
                values = [getattr(entity, f.name) for f in dataclasses.fields(entity)] if dataclasses.is_dataclass(entity) else list(vars(entity).values())
                if any(str(value) == real for value in values):
                    return real
        return None


def run_ids(surface: Surface, model: Model) -> Identities:
    client = getattr(surface, "client", None)
    return client.ids if isinstance(client, Client) else Held(model)


def ownership(shape: Shape | None, value: object, ids: Identities) -> tuple[int, int]:
    """How many ids of a detail the run made, and how many it did not."""
    if isinstance(shape, Id):
        if value is None:
            return 0, 0
        return (1, 0) if ids.model_of(shape.kind, str(value)) is not None else (0, 1)
    if isinstance(shape, List) and isinstance(value, list):
        counts = [ownership(shape.of, item, ids) for item in value]
        return sum(c[0] for c in counts), sum(c[1] for c in counts)
    if isinstance(shape, Object) and isinstance(value, dict):
        counts = [ownership(spec.shape, value.get(name), ids) for name, spec in shape.fields.items()]
        return sum(c[0] for c in counts), sum(c[1] for c in counts)
    return 0, 0


def plain(value: object) -> object:
    if isinstance(value, dict):
        return {k: plain(v) for k, v in cast("dict[str, object]", value).items()}
    if isinstance(value, (list, tuple)):
        return tuple(plain(v) for v in cast("Iterable[object]", value))
    return value


def differences(want: dict[str, Any], got: object, where: str = "") -> list[str]:
    """Each path the book predicts whose value the tapped detail does not hold, with both values."""
    out: list[str] = []
    for name, expected in want.items():
        path = f"{where}.{name}" if where else name
        held = cast("dict[str, object]", got).get(name) if isinstance(got, dict) else None
        if isinstance(expected, dict):
            out += differences(cast("dict[str, Any]", expected), held, path)
        elif plain(expected) != plain(held):
            out.append(f"{path} tapped {held!r}, the book says {expected!r}")
    return out


def emissions(action: type[Action[Any, Any]], request: object, model: Model, surface: Surface) -> str:
    """The note of the first event the action should emit and the tap did not show, or nothing."""
    if not Deliveries.tapping:
        Deliveries.unproven += len(action.emits)
        return ""
    ids = run_ids(surface, model)
    by = getattr(request, "by", SOLE)
    accepted = action.take(cast(Any, request).input())
    for event in action.emits:
        wanted = action.announces(event, accepted, model, by) or {}
        note = Deliveries.prove(event, wanted, ids, action.__name__)
        if note:
            Deliveries.failed_emissions += 1
            return note
        Deliveries.proven += 1
    return ""


class Landings:
    """What this run has seen of how long an event takes to land: the most
    reads one took, and whether one never landed."""

    longest = 0
    missed = False

    @classmethod
    def bound(cls) -> int:
        """How many reads the next event gets. Until an event fails to land,
        every one gets `RETAKES`. After that the run is red already, and an
        event gets three times the longest landing seen, so the cells behind a
        broken consumer fail in seconds each."""
        return max(3 * cls.longest, PATIENCE) if cls.missed else RETAKES


def spoken(surface: Surface, outcome: Outcome) -> Outcome:
    """A refusal as the two sides are compared. The app's message arrives with
    each id the app issued read as the model's id. The model's message is read
    the same way here, so a message that quotes an id the caller typed as the
    app knows it compares equal on both sides."""
    ids = getattr(getattr(surface, "client", None), "ids", None)
    if isinstance(outcome, Refusal) and ids is not None:
        return replace(outcome, message=ids.spoken(outcome.message))
    return outcome


def landed(surface: Surface, wanted: tuple[object, ...]) -> tuple[tuple[object, ...], int]:
    """An outside event may land after the call that caused it, and in more
    than one write. The watch is read again until it shows what the model says,
    at most `Landings.bound()` times, and the last reading is the one judged: a
    reading off its shape on the way there is the event half landed. Each read
    is a round trip, so nothing sleeps and nothing reads a clock."""
    got: tuple[object, ...] = ()
    most = Landings.bound()
    for reads in range(1, most + 1):
        try:
            got = surface.rows()
        except (Undeclared, OffShape):
            if reads == most:
                Landings.missed = True
                raise
            continue
        if got == wanted:
            Landings.longest = max(Landings.longest, reads)
            return got, reads
    Landings.missed = True
    return got, most


def defect_answered(defect: Defect[Any, Any], app: Outcome) -> bool:
    """The app answered what the defect declares: a success for a status under
    400, else the refusal word for word."""
    if not turned_away(defect.status):
        return isinstance(app, Done)
    return (isinstance(app, Refusal) and app.message == defect.message
            and (app.status == 0 or app.status == defect.status))


def flawed(step: object, model_outcome: Flawed, app_outcome: Outcome, model: Model, surface: Surface,
           reduced: str) -> StepResult:
    """A call on which a declared defect shows. The app answering the defect is
    known, the app answering what was meant means the defect is gone, and the
    model then takes the change so later steps stay honest."""
    defect = model_outcome.defect
    if defect_answered(defect, app_outcome):
        if model_outcome.wrong is not None:
            model.undergo(model_outcome)
        model_rows, app_rows = listing(surface, model), surface.rows()
        if model_rows == app_rows:
            return StepResult(step, model_outcome, app_outcome, model_rows, app_rows, True,
                              f"known defect: {defect.status} {defect.message}", reduced, known=defect)
        note = "rows differ after the defect: model " + str([str(r) for r in model_rows]) + " app " + str([str(r) for r in app_rows])
        return StepResult(step, model_outcome, app_outcome, model_rows, app_rows, False, note, reduced)
    model_rows, app_rows = listing(surface, model), surface.rows()
    if agree(spoken(surface, model_outcome.meant), app_outcome):
        model.adopt(model_outcome)
        model_rows = listing(surface, model)
        if model_rows == app_rows:
            note = f"the defect no longer shows, delete its declaration: {defect.status} {defect.message}"
        else:
            note = (f"the defect no longer shows, delete its declaration: {defect.status} {defect.message}; "
                    "rows differ: model " + str([str(r) for r in model_rows]) + " app " + str([str(r) for r in app_rows]))
        return StepResult(step, model_outcome, app_outcome, model_rows, app_rows, False, note, reduced)
    note = f"model said {model_outcome}, app said {app_outcome}"
    return StepResult(step, model_outcome, app_outcome, model_rows, app_rows, False, note, reduced)


class Deliveries:
    """The way events reach the service in this run, as the environment names it. Class state, like `Landings`: a
    run is one process."""

    role: Delivery | None = None
    delivered = 0
    declared = 0
    failed = 0
    proven = 0
    failed_emissions = 0
    unproven = 0
    tapping = False
    cannot = False
    buffer: list[tuple[str, Any]] = []
    hooked = False
    handler: Any = None

    @classmethod
    def begin(cls, role: Delivery | None) -> None:
        cls.close()
        cls.role = role
        cls.delivered = cls.declared = cls.failed = 0
        cls.proven = cls.failed_emissions = cls.unproven = 0
        cls.cannot = False
        cls.buffer = []

    @classmethod
    def watch(cls) -> None:
        """Opens the tap the first time an action that emits is about to be taken. An environment that names no delivery,
        or one that cannot tap, leaves the emissions unproven."""
        if cls.tapping or cls.cannot or cls.role is None:
            return
        try:
            cls.role.open_tap()
        except NotImplementedError:
            cls.cannot = True
            return
        cls.tapping = True
        if not cls.hooked:
            atexit.register(cls.close)
            cls.hooked = True
        try:
            cls.handler = signal.signal(signal.SIGTERM, cls.terminated)
        except ValueError:
            cls.handler = None

    @staticmethod
    def terminated(signum: int, frame: object) -> None:
        raise SystemExit(128 + signum)

    @classmethod
    def close(cls) -> None:
        """Removes what the tap made. Safe to call when no tap is open."""
        if not cls.tapping:
            return
        cls.tapping = False
        if cls.handler is not None:
            signal.signal(signal.SIGTERM, cls.handler)
            cls.handler = None
        if cls.role is not None:
            cls.role.close_tap()

    @classmethod
    def prove(cls, event: type[Event], wanted: dict[str, Any], ids: Identities, name: str) -> str:
        """Reads the tap again, at most `Landings.bound()` times, until an event of this name about a record the run made
        agrees with what the action announces. The events about the run's records that matched nothing stay buffered."""
        assert cls.role is not None and event.detail is not None
        most = Landings.bound()
        off: list[str] = []
        for reads in range(1, most + 1):
            for tapped, detail in cls.role.tapped():
                owned, strange = ownership(event.detail, detail, ids)
                if owned or not strange:
                    cls.buffer.append((tapped, canonical(event.detail, detail, app=True, ids=ids, where=event.name)))
            off = []
            for position, (tapped, seen) in enumerate(cls.buffer):
                if tapped != event.name:
                    continue
                off = differences(wanted, seen)
                if not off:
                    del cls.buffer[position]
                    Landings.longest = max(Landings.longest, reads)
                    return ""
        Landings.missed = True
        if not off:
            return f"{name} should emit {event.name} about a record this run made; the tap read none in {most} reads"
        return f"{name} emitted {event.name} but it disagrees with the book: " + "; ".join(off)

    @classmethod
    def line(cls) -> str:
        """The run's second deliveries and emissions, or nothing when no hearing was delivered and no action emitted."""
        lines = []
        if cls.delivered:
            lines.append(f"repeats: {cls.delivered} delivered, {cls.declared} applied again as declared, {cls.failed} fail")
        if cls.proven or cls.failed_emissions or cls.unproven:
            lines.append(f"emissions: {cls.proven} proven, {cls.failed_emissions} fail, {cls.unproven} unproven")
        return "\n".join(lines)
