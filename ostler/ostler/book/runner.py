"""Walks a journey on the model and on the surface, step by step, and records
whether the app did what the model says it does, and what the model reduced
each step to."""

from __future__ import annotations

from typing import Any, Callable, Iterable, cast

from ostler.book.arrange import Arrange
from ostler.book.backstage import CannotArrange
from ostler.book.errors import BookError, Unhealthy
from ostler.book.http import OffShape, Undeclared
from ostler.book.journey import (Check, Given, Journey, JourneyResult, Listed, Refused, Relates, Same, Seen, Shows,
                                 StepResult, Undo, difference, masked)
from ostler.book.model import Defect, Model
from ostler.book.outcome import CannotReach, Done, Flawed, Outcome, Refusal, Unreachable
from ostler.book.status import refused as turned_away
from ostler.book.surface import Surface


RETAKES = 1000
PATIENCE = 50


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
                if given.undo is not None:
                    attempt(Undo(given), model, surface, baseline)
    result.state = model.describe()
    return result


def attempt(step: object, model: Model, surface: Surface, baseline: tuple[object, ...] = (),
            seen: dict[int, Seen] | None = None) -> StepResult:
    """Takes one step on both sides and turns anything that escapes into a failed step.
    The step's text is read before it is taken: a fixture moves on with later steps."""
    text = str(step)
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
    result.text = text
    stray = strays(surface)
    if stray and not result.skipped:
        note = "the page sent a request no screen declares: " + ", ".join(stray)
        result.note = f"{result.note}; {note}" if result.note else note
        result.ok = False
    return result


def strays(surface: Surface) -> list[str]:
    ask = getattr(surface, "strays", None)
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
    if isinstance(step, Check):
        probed = step.probe(surface)
        return StepResult(step, None, None, model.rows(), (), probed is None, probed or "")
    if isinstance(step, Undo):
        return perform(step, step.given.undo, model, surface)
    if isinstance(step, Given):
        return perform(step, step.request, model, surface)
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
    try:
        outcome = surface.perform(step)
    except CannotReach as blocked:
        outcome = Unreachable(blocked.reason)
    ok = isinstance(outcome, Done)
    rows = outcome.rows if isinstance(outcome, Done) else ()
    remember(step, surface, rows, seen)
    return StepResult(step, None, outcome, model.rows(), rows, ok, "" if ok else f"app said {outcome}")


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


def perform(step: object, request: object, model: Model, surface: Surface) -> StepResult:
    model_outcome = model.perform(request)
    reduced = trace(model)
    try:
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
    if callable(express) and isinstance(model_outcome, Done) and isinstance(app_outcome, Done):
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
    return StepResult(step, model_outcome, app_outcome, model_rows, app_rows, ok, note, reduced)


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
    if agree(model_outcome.meant, app_outcome):
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
