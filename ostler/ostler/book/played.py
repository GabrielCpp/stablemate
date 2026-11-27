"""Which plays exercised each stated element of a book, and the report of the ones no play did. A play is a journey, a
matrix cell or an input class, named as the run names it."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence, cast

from ostler.book.arrange import Arrange
from ostler.book.cells import Played
from ostler.book.domain import Action
from ostler.book.exploration import declared_rules
from ostler.book.inputs import Tried
from ostler.book.journey import Given, JourneyResult, StepResult
from ostler.book.model import Rule
from ostler.book.outcome import Done, Flawed, Refusal
from ostler.book.tapping import Deliveries
from ostler.book.search import actions_of
from ostler.book.service import Service
from ostler.book.witness import ENDPOINT, Unseen

OUTSIDE = "outside happening"
ACTION = "action"
RULE = "rule"
SCENE = "scene"
KINDS = (OUTSIDE, ACTION, RULE, SCENE)
ANYTHING = ("*", "*")
EVERYTHING = ("all", "all")
HEADLINE = "Stated and never played"

CLOSES = {
    OUTSIDE: "no step, cell or given arranges it; arrange it in a journey or a matrix",
    ACTION: "no play reached the app through it and had the model accept the call; take it in a journey step, a cell or an input class",
    RULE: "no play drew this refusal and saw the app agree; draw it in a journey step, a cell or an input class",
    SCENE: "no cell arranged it; give the matrix an action that is built there",
}


class PlayedBy:
    """For each kind of stated element, each element by name, and the plays that exercised it in the order the run met them."""

    def __init__(self) -> None:
        self.by: dict[str, dict[str, list[str]]] = {kind: {} for kind in KINDS}

    def stated(self, kind: str, name: str) -> None:
        self.by[kind].setdefault(name, [])

    def add(self, kind: str, name: str, play: str) -> None:
        plays = self.by[kind].setdefault(name, [])
        if play not in plays:
            plays.append(play)

    def never(self, kind: str) -> list[str]:
        return [name for name, plays in self.by[kind].items() if not plays]

    def step(self, play: str, result: StepResult) -> None:
        """What one step of a play exercised: the happening it arranged, the action the model accepted, the rule it drew."""
        if not result.ok or result.skipped:
            return
        request = result.step.request if isinstance(result.step, Given) else result.step
        if isinstance(request, Arrange):
            self.add(OUTSIDE, type(request).__name__, play)
        action = getattr(type(request), "carries", None)
        if isinstance(action, type) and issubclass(action, Action) and isinstance(result.model, (Done, Flawed)):
            if isinstance(result.model, Flawed) and result.model.defect.over is not None:
                self.add(RULE, result.model.defect.over.name, play)
            else:
                self.add(ACTION, action.__name__, play)
        if isinstance(result.model, Refusal) and isinstance(result.model.rule, Rule):
            self.add(RULE, result.model.rule.name, play)

    def save(self, folder: str, name: str) -> None:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{name}-played.json"), "w") as f:
            json.dump({kind: {n: self.by[kind][n] for n in sorted(self.by[kind])} for kind in sorted(self.by)}, f, indent=2)
            f.write("\n")


def stated_by(service: Service[Any], module: str) -> PlayedBy:
    """A record with every outside happening, action, rule and scene the book states, and no play yet."""
    found = PlayedBy()
    for outside in service.outside:
        found.stated(OUTSIDE, outside.__name__)
    actions = actions_of(service, module)
    for action in actions:
        if any(other is not action and issubclass(other, action) for other in actions):
            continue
        found.stated(ACTION, action.__name__)
        for rule in action.rules:
            found.stated(RULE, rule.name)
    for endpoint in (*service.endpoints, *service.interactions):
        for gate in getattr(endpoint, "gates", ()):
            found.stated(RULE, gate.name)
    for name in declared_rules(service, service.new_model(date.today())):
        found.stated(RULE, name)
    for axes in service.matrices:
        for scene in axes.scenes:
            found.stated(SCENE, f"{axes.record}:{scene.name}")
    return found


def record(found: PlayedBy, results: Sequence[JourneyResult], cells: Played, tried: Tried) -> None:
    """Fills the record from what the run already holds: the steps of each journey, of each cell, and each input class sent."""
    for result in results:
        for step in result.steps:
            found.step(result.journey.title(), step)
    for cell in cells.cells:
        for step in cell.steps:
            found.step(cell.text, step)
        if cell.arranged:
            found.add(SCENE, f"{cell.record}:{cell.scene}", cell.text)
    for sent in tried.sent:
        if sent.taken is not None:
            found.step(sent.text, sent.taken)


def named_by(request: object) -> Iterable[tuple[str, str]]:
    request = request.request if isinstance(request, Given) else request
    if isinstance(request, Arrange):
        yield OUTSIDE, type(request).__name__
    action = getattr(type(request), "carries", None)
    if isinstance(action, type) and issubclass(action, Action):
        yield ACTION, action.__name__


def skipped_names(results: Sequence[JourneyResult], cells: Played, tried: Tried, day: date) -> set[tuple[str, str]]:
    """What a skipped play could have exercised, read from the book: the happenings and actions its steps name and the
    scene of a skipped cell. Any skip also puts the rules out of reach, for a skipped play may have drawn any of them."""
    out: set[tuple[str, str]] = set()
    for result in results:
        if not result.skipped:
            continue
        out.add(ANYTHING)
        try:
            for step in (*result.journey.given, *result.journey().steps(day)):
                out.update(named_by(step))
        except Exception:
            out.add(EVERYTHING)
    for cell in cells.cells:
        if cell.skipped:
            out.update((ANYTHING, (SCENE, f"{cell.record}:{cell.scene}")))
    for sent in tried.sent:
        if sent.skipped:
            action = getattr(sent.endpoint, "carries", None)
            out.update((ANYTHING, *(((ACTION, action.__name__),) if action is not None else ())))
    return out


def carriers(service: Service[Any], action: str) -> tuple[list[str], list[str]]:
    """The endpoints and interactions that carry an action, and the outside happenings that do."""
    calls = [e.__name__ for e in (*service.endpoints, *service.interactions) if getattr(e, "carries", None) is not None
             and cast(type, e.carries).__name__ == action]
    outside = [o.__name__ for o in service.outside if o.carries is not None and o.carries.__name__ == action]
    return calls, outside


def tapped() -> bool:
    return Deliveries.role is not None and not Deliveries.cannot


FORMS = "Because.RUNTIME | OUTSIDE | NO_ACCOUNT"
VARIABLES = {RULE: "<rule variable>", SCENE: "<scene variable>"}


@dataclass
class Section:
    """The report section as lines, and the items that make the run red: what no play exercised and the book does not
    declare, and a declaration the run contradicts."""

    lines: list[str]
    red: list[str] = field(default_factory=list)


def declared_as(service: Service[Any]) -> dict[tuple[str, str], Unseen]:
    """The declarations of the book about outside happenings, actions, rules and scenes, by kind and the name the record uses."""
    scenes = {id(scene): f"{axes.record}:{scene.name}" for axes in service.matrices for scene in axes.scenes}
    out: dict[tuple[str, str], Unseen] = {}
    for unseen in service.unseen:
        if unseen.kind == ENDPOINT:
            continue
        name = scenes.get(id(unseen.of), f"?{unseen.name}") if unseen.kind == SCENE else unseen.name
        out[(unseen.kind, name)] = unseen
    return out


def covered_by_defects(actions: Sequence[type[Action[Any, Any]]]) -> set[str]:
    return {d.over.name for action in actions for d in action.defects if d.over is not None}


def never_played(service: Service[Any], found: PlayedBy, actions: Sequence[type[Action[Any, Any]]], scoped: bool,
                 skipped: set[tuple[str, str]], streaming: Sequence[str] = ()) -> Section:
    """The section of the report. A scoped run judged nothing. A skipped play leaves what it could have exercised, and every
    rule, under `not judged here`."""
    if scoped:
        return Section([f"{HEADLINE}: not judged on a partial run", *streaming])
    unjudged = {(kind, name) for kind in KINDS for name in found.never(kind)
                if EVERYTHING in skipped or (kind, name) in skipped or (kind == RULE and ANYTHING in skipped)}
    never = {kind: [n for n in found.never(kind) if (kind, n) not in unjudged] for kind in KINDS}
    declared = declared_as(service)
    defects = covered_by_defects(actions)
    outside = {o.__name__: o for o in service.outside}
    streams = {e.__name__ for e in service.endpoints if getattr(e, "streams", None)}
    lines: list[str] = []
    red: list[str] = []
    for kind in KINDS:
        for name in never[kind]:
            if kind == RULE and name in defects:
                continue
            if kind == ACTION:
                calls, hearings = carriers(service, name)
                if not calls and hearings and all(h in never[OUTSIDE] or (OUTSIDE, h) in unjudged for h in hearings):
                    continue
                if calls and not hearings and all(c in streams for c in calls):
                    continue
            if (kind, name) in declared:
                unseen = declared[(kind, name)]
                lines.append(f"- {kind} {name} declared unseen ({unseen.because.name}): {unseen.why}")
                continue
            note = CLOSES[kind]
            if kind == OUTSIDE and name in outside and outside[name].carries is not None:
                carried = outside[name].carries
                if carried is not None and carried.__name__ in found.never(ACTION) and not carriers(service, carried.__name__)[0]:
                    note += f"; it carries {carried.__name__}"
            lines.append(f"- {kind} {name}: {note}; or declare it: Unseen({VARIABLES.get(kind, name)}, {FORMS}, \"why\")")
            red.append(f"{kind} {name}")
    for (kind, name), unseen in declared.items():
        if (kind, name) in unjudged:
            continue
        plays = found.by[kind].get(name)
        if plays:
            lines.append(f"- {kind} {name}: declared unseen but played by {', '.join(plays)}; delete the declaration (fails the run)")
        elif plays is None:
            lines.append(f"- {kind} {name.removeprefix('?')}: declared unseen but the book states no such {kind}; delete the declaration (fails the run)")
        else:
            continue
        red.append(f"{kind} {name.removeprefix('?')} declared")
    emitted = [f"{event.name} ({action.__name__})" for action in actions if found.by[ACTION].get(action.__name__) for event in action.emits]
    if emitted and not tapped():
        lines.append(f"- events with no tap: the environment names no delivery tap, so no run sees {', '.join(emitted)} emitted; "
                     "a delivery that taps closes it")
    lines += [f"- {line}" for line in streaming]
    if unjudged:
        lines.append("  not judged here:")
        lines += [f"    - {kind} {name}" for kind in KINDS for name in found.never(kind) if (kind, name) in unjudged]
    return Section([HEADLINE, *lines] if lines else [f"{HEADLINE}: nothing"], red)
