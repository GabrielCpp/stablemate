"""The book checked before it runs: everything the commands build from the
declarations is built once, with no stack, and anything that raises or comes
out without its text is a finding that names the object."""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator, cast

from ostler._vendor.stablemate_core import config as core_config
from ostler.book import decisions, questions
from ostler.book.arrange import Arrange
from ostler.book.explore import _overrides, attempts, moves
from ostler.book.graph import dot
from ostler.book.boundary import Foreign, Needs
from ostler.book.entries import says
from ostler.book.http import Endpoint, List, Object, Str, bare_ids, states
from ostler.book.tree import unresolved
from ostler.book.journey import Given, Journey, OwnerRefused, Refused
from ostler.book.model import Rule
from ostler.book.inputs import bases, body_fields, classes, expected, has_inputs, passed_on as passes_call, plays, predicted, refusals_for, states_shape, vary
from ostler.book.errors import BookError
from ostler.book.matrix import cell, matrix
from ostler.book.state import Impossible
from ostler.book.outcome import Done
from ostler.book.status import succeeded
from ostler.book.screen import Component, Interaction, as_label
from ostler.book.search import actions_of, items, states_of
from ostler.book.service import Service
from ostler.book.sources import elements, file_of, missing, pointer_missing


@dataclass(frozen=True)
class Finding:
    """One thing the check says of a book. `blocks` stops a run. `told` only informs: the check prints it as a note and still passes."""

    name: str
    problem: str
    blocks: bool = True
    told: bool = False

    def __post_init__(self) -> None:
        if self.told and self.blocks:
            object.__setattr__(self, "blocks", False)

    def __str__(self) -> str:
        return f"{self.name}: {self.problem}"


def attempt(found: list[Finding], name: str, build: Callable[[], Any], required: bool = False) -> None:
    """Builds one thing and records what went wrong with it."""
    try:
        built = build()
    except Exception as crash:
        found.append(Finding(name, f"{type(crash).__name__}: {str(crash).splitlines()[0] if str(crash) else ''}"))
        return
    if required and not str(built).strip():
        found.append(Finding(name, "empty text"))


def given_model(service: Service[Any], journey: type[Journey]) -> Any:
    """A new model with the journey's `Given` requests performed on it and the records a screen book needs taken in from their owners."""
    from ostler.book.owners import Owners

    model = service.new_model(date.today())
    for given in journey.given:
        if isinstance(given, Given):
            model.perform(given.request)
        elif isinstance(given, Needs) and given.foreign.takes is not None:
            Owners.seed(given, model)
    return model


def exercised(service: Service[Any]) -> Iterator[tuple[str, Any, list[str], Any]]:
    """Every endpoint call the journeys make, replayed on the model alone: where
    it is, the call, the ids it sends where another kind is typed, and what the
    model answered."""
    for journey in service.journeys:
        model = given_model(service, journey)
        for step in journey().steps(model.today):
            if isinstance(step, Endpoint) and step.carries is not None:
                faults = step.id_faults(model)
                try:
                    outcome = model.perform(step)
                except Exception:
                    break
                yield f"journey {journey.__name__}: {step}", step, faults, outcome


def identity_faults(service: Service[Any]) -> list[Finding]:
    found: list[Finding] = []
    for endpoint in service.endpoints:
        if endpoint.carries is None:
            continue
        for shape, place in ((endpoint.params, "path"), (endpoint.query, "query"), (endpoint.body, "body")):
            found += [Finding(f"endpoint {endpoint.__name__}", p) for p in bare_ids(shape, place)]
        for answer in endpoint.answers:
            if succeeded(answer.status):
                found += [Finding(f"endpoint {endpoint.__name__}", p) for p in bare_ids(answer.body, f"answer {answer.status}")]
    for where, step, faults, outcome in exercised(service):
        found += [Finding(where, fault) for fault in faults]
        if isinstance(outcome, Done):
            found += [Finding(where, fault) for fault in step.view_faults(outcome.view)]
    if service.endpoints:
        fresh = service.new_model(date.today())
        for step in moves(service.endpoints, cast=service.cast)(fresh):
            found += [Finding(f"plan move {step}", fault) for fault in step.id_faults(fresh)]
    return found


def itself_faults(service: Service[Any]) -> list[Finding]:
    """Every `Itself` that names no enclosing object, in the shapes the endpoints declare."""
    found: list[Finding] = []
    for endpoint in service.endpoints:
        for shape, place in ((endpoint.params, "path"), (endpoint.query, "query"), (endpoint.headers, "headers"), (endpoint.body, "body")):
            found += [Finding(f"endpoint {endpoint.__name__}", p) for p in unresolved(shape, place)]
        for answer in endpoint.answers:
            found += [Finding(f"endpoint {endpoint.__name__}", p) for p in unresolved(answer.body, f"answer {answer.status}")]
    return found


def header_faults(service: Service[Any]) -> list[Finding]:
    found: list[Finding] = []
    for endpoint in service.endpoints:
        action = endpoint.carries
        if action is None:
            continue
        name = f"endpoint {endpoint.__name__}"
        if endpoint.headers is not None and not action.hears:
            found.append(Finding(name, f"declares headers {', '.join(endpoint.headers.fields)} but {action.__name__} "
                                 "does not hear them: set hears = True and reduce over Heard, or drop the header"))
        if endpoint.headers is None and action.hears:
            found.append(Finding(name, f"{action.__name__} hears headers but the endpoint declares none"))
    return found


def clock_faults(service: Service[Any]) -> list[Finding]:
    found: list[Finding] = []
    for endpoint in service.endpoints:
        action = endpoint.carries
        if action is not None and action.clock:
            found.append(Finding(f"endpoint {endpoint.__name__}", f"carries {action.__name__}, which the clock causes ({action.clock!r}): "
                                 "carry it from an Arrange the journey takes after the record is past its moment, or drop clock"))
    for outside in service.outside:
        action = outside.carries
        if outside.heard is not None and action is not None and action.clock:
            found.append(Finding(f"outside {outside.__name__}", f"hears {outside.heard.name} and carries {action.__name__}, which the clock causes "
                                 f"({action.clock!r}): split it in two, one Arrange that hears the event and one that carries the clocked action"))
    return found


def defect_faults(service: Service[Any]) -> list[Finding]:
    carried: dict[Any, list[type[Endpoint]]] = {}
    for endpoint in service.endpoints:
        if endpoint.carries is not None:
            carried.setdefault(endpoint.carries, []).append(endpoint)
    found: list[Finding] = []
    for action, endpoints in carried.items():
        for defect in action.defects:
            rule = defect.breaks
            if rule is None or any(states(answer.body, rule) for e in endpoints for answer in e.answers):
                continue
            found.append(Finding(f"action {action.__name__}", f"the defect {defect.message!r} breaks {says(rule)}, but no list in the answers of "
                                 f"{', '.join(e.__name__ for e in endpoints)} states that rule: add it to the entries of the list it judges"))
    return found


def input_faults(service: Service[Any]) -> list[Finding]:
    found: list[Finding] = []
    skipped = {u.endpoint for u in service.unseen if u.item == "inputs"}
    reached = bases(service)
    labels: dict[type[Any], set[str]] = {}
    for endpoint in (*service.endpoints, *service.interactions):
        if not plays(endpoint) or not has_inputs(endpoint):
            continue
        name = f"{'interaction' if issubclass(endpoint, Interaction) else 'endpoint'} {endpoint.__name__}"
        base = reached.get(endpoint)
        if endpoint in skipped:
            if base is not None:
                found.append(Finding(name, "inputs are declared unseen, but a step reaches it: delete the declaration"))
            continue
        if base is None and issubclass(endpoint, Endpoint) and passes_call(endpoint) and endpoint.body is None:
            continue
        if base is None:
            found.append(Finding(name, "no journey step or matrix cell makes a call the model accepts, so its input "
                                 "classes have no base: add one, or declare Unseen(endpoint, 'inputs', Because.<reason>, why)"))
            continue
        for c in classes(base.call, base.before, None):
            labels.setdefault(endpoint, set()).add(c.label)
            try:
                call = vary(base.call, c)
            except Exception as crash:
                found.append(Finding(name, f"{c.label} cannot be built: {type(crash).__name__}: {crash}"))
                continue
            declared = any(d.endpoint is endpoint and d.label == c.label for d in service.diverges)
            try:
                said = predicted(call, base.before)
            except BookError as wrong:
                found.append(Finding(name, f"{c.label}: {wrong}"))
                continue
            if not expected(c, said) and not declared and refusals_for(service, endpoint).of(c.default) is None:
                found.append(Finding(name, f"{c.label}: the model has no rule and the book declares no {c.default} refusal"))
    for d in service.diverges:
        if d.label not in labels.get(d.endpoint, set()):
            found.append(Finding(f"diverges {d}", "no input class of the endpoint has this label"))
    return found


def source_faults(service: Service[Any], app: str | None) -> list[Finding]:
    found = [Finding(e.__name__, "no source pointer", blocks=False) for e in elements(service)
             if not cast(Any, e).source and not (e in service.interactions and cast(Any, e).screen is None)]
    members = core_config.workspace_members()
    for name, path in missing(service, app):
        member = path.removeprefix("repo://").partition("/")[0] if path.startswith("repo://") else ""
        if not member:
            found.append(Finding(name, f"source {path} does not exist under {app}"))
        elif member in members:
            found.append(Finding(name, f"source {path} does not exist"))
        else:
            found.append(Finding(name, f"source {path} names no checkout"))
    return found


COMMIT = re.compile(r"[0-9a-f]{7,40}")
COMMIT_FILE = re.compile(r"([0-9a-f]{7,40}):(.+)")


def commit_has(app: str, spec: str) -> bool:
    return subprocess.run(["git", "-C", app, "cat-file", "-e", spec], capture_output=True).returncode == 0


def source_is_there(pointer: str, app: str, members: dict[str, Path]) -> bool:
    if COMMIT.fullmatch(pointer):
        return commit_has(app, f"{pointer}^{{commit}}")
    named = COMMIT_FILE.fullmatch(pointer)
    if named:
        return commit_has(app, pointer)
    return not pointer_missing(file_of(pointer), app, members)


def decision_faults(service: Service[Any], module: str, app: str | None = None) -> list[Finding]:
    found: list[Finding] = []
    members = core_config.workspace_checkouts(Path(app)) if app else {}
    known = decisions.resolve(service, module)
    for d in decisions.load(module):
        name = f"decision {d.slug}"
        if not d.story:
            found.append(Finding(name, "no story", blocks=False))
        if not d.date:
            found.append(Finding(name, "no date", blocks=False))
        if not d.elements:
            found.append(Finding(name, "names no element", blocks=False))
        found += [Finding(name, f"element {e} resolves to no element of the book", blocks=False)
                  for e in d.elements if e not in known]
        if app is not None:
            found += [Finding(name, f"source {s} is not there", blocks=False)
                      for s in d.sources if not source_is_there(s, app, members)]
    return found


def question_faults(service: Service[Any], module: str) -> list[Finding]:
    known = decisions.resolve(service, module)
    unread = [Finding(f"question line {n}", "is no entry, write it as `- <Element>: <question>`", blocks=False)
              for n in questions.unread(module)]
    return unread + [Finding(f"question line {q.line}", f"element {q.element} resolves to no element of the book", blocks=False)
                     for q in questions.load(module) if q.element not in known]


def defined(module: str, base: type) -> list[type]:
    """Every subclass of `base` a loaded module of the book package defines."""
    return [cls for name, loaded in list(sys.modules.items()) if name == module or name.startswith(module + ".")
            for cls in vars(loaded).values()
            if isinstance(cls, type) and issubclass(cls, base) and cls is not base and cls.__module__ == name]


def unregistered(module: str, base: type, registered: tuple[type, ...], where: str) -> list[Finding]:
    bases = {b for r in registered for b in r.__mro__}
    return [Finding(f"{base.__name__.lower()} {cls.__name__}", f"defined in {cls.__module__} but {where} does not list it: register it or delete it")
            for cls in defined(module, base) if cls not in registered and cls not in bases]


def registration_faults(service: Service[Any], module: str) -> list[Finding]:
    """What the book package holds that nothing the service loads reaches: a module no import
    touches, an endpoint, journey or outside event its lists leave out, a rule no action or
    state carries, and two endpoints that collapse into one name or one route."""
    found: list[Finding] = []
    package = importlib.import_module(module)
    for info in pkgutil.walk_packages(package.__path__, module + "."):
        if info.name not in sys.modules:
            found.append(Finding(f"module {info.name}", "nothing the service loads imports it: register what it defines or delete it"))
    found += unregistered(module, Endpoint, service.endpoints, "service.endpoints")
    found += unregistered(module, Journey, (*service.journeys, *service.health), "service.journeys or service.health")
    stepped = tuple({type(step) for journey in service.journeys for step in journey().steps(given_model(service, journey).today) if isinstance(step, Arrange)})
    found += unregistered(module, Arrange, (*service.outside, *stepped), "service.outside or a journey step")
    carried = {id(r) for a in actions_of(service, module) for r in a.rules} | {id(r) for s in states_of(service) for r in s.rules}
    try:
        rules = importlib.import_module(f"{module}.model.rules")
    except ModuleNotFoundError:
        rules = None
    if rules is not None:
        for name, value in vars(rules).items():
            if isinstance(value, Rule) and id(value) not in carried:
                found.append(Finding(f"rule {name}", f"defined in {rules.__name__} but no action or state carries it: attach it or delete it"))
    names: dict[str, type] = {}
    routes: dict[str, type] = {}
    for endpoint in service.endpoints:
        if endpoint.__name__ in names:
            found.append(Finding(f"endpoint {endpoint.__name__}", f"shares its name with {names[endpoint.__name__].__module__}.{endpoint.__name__}: exploration keys cells by name, so one hides the other"))
        names.setdefault(endpoint.__name__, endpoint)
        route = endpoint.route()
        if route in routes:
            found.append(Finding(f"endpoint {endpoint.__name__}", f"answers {route}, the route of {routes[route].__name__}: merge them or give one its own route"))
        routes.setdefault(route, endpoint)
    return found


def delivery_faults(service: Service[Any], module: str) -> list[Finding]:
    """A hearing that builds a detail is delivered only where an environment names a delivery, and a delivery serves only such a hearing."""
    building = [o for o in service.outside if o.delivers()]
    delivering = [e for e in service.environments.values() if e.delivery is not None]
    out: list[Finding] = []
    if building and not delivering:
        out += [Finding(f"outside {module}.{o.__name__}", "builds the detail of its event and no environment names a delivery: "
                        "the hearing is performed by the surface until an environment names a delivery", told=True) for o in building]
    if delivering and not building:
        out += [Finding(f"environment {e.name}", "names a delivery and no outside event builds a detail: nothing is delivered "
                        "until a hearing defines detail", told=True) for e in delivering]
    return out


def event_faults(service: Service[Any], module: str) -> list[Finding]:
    """What this book's events and outside events say that another book under the root contradicts or leaves unanswered."""
    from ostler.book.event import bare
    from ostler.book.eventmap import books, hearers, owner_of

    out = delivery_faults(service, module)
    if not service.events and not any(o.heard is not None for o in service.outside):
        return out
    found, skipped = books(module, service)
    out += [Finding(f"book {name}", f"cannot be loaded, so its events are not read: {why}", blocks=False) for name, why in skipped.items()]
    declared: dict[str, dict[type, set[str]]] = {}
    for name, book in found.items():
        for event in (*book.events, *(o.heard for o in book.outside if o.heard is not None)):
            declared.setdefault(event.name, {}).setdefault(event, set()).add(name)
    for event_name, rivals in declared.items():
        if len(rivals) > 1 and any(module in named for named in rivals.values()):
            where = " and ".join(f"{cls.__module__}.{cls.__qualname__} ({', '.join(sorted(named))})" for cls, named in rivals.items())
            out.append(Finding(f"event {event_name}", f"is declared as {len(rivals)} different classes, {where}: import the emitter's class instead of declaring it again"))
    emitted = {e.name for name, book in found.items() for action in actions_of(book, name) for e in action.emits}
    for outside in service.outside:
        event = outside.heard
        if event is None:
            continue
        for path in outside.reads:
            if bare(path) not in event.paths():
                out.append(Finding(f"outside {module}.{outside.__name__}",
                                   f"reads {path}, which event {event.name} of {owner_of(found, event)} does not declare"))
        if event.name not in emitted and not event.owner:
            out.append(Finding(f"outside {module}.{outside.__name__}",
                               f"hears {event.name}, which no action under the root emits: add emits to the action that results in it, "
                               "or declare the event in this book with owner = <who emits it>", blocks=False))
    for event in service.events:
        if not event.owner and not hearers(found, event):
            out.append(Finding(f"event {event.name}", f"is owned by {module} and no outside event under the root hears it", blocks=False))
    return out


def references(module: str, service: Service[Any]) -> list[Foreign]:
    """Every `Foreign` a book states: one a module of the book holds, and one a journey needs."""
    found: dict[int, Foreign] = {}
    for name, loaded in list(sys.modules.items()):
        if name == module or name.startswith(module + "."):
            for value in list(vars(loaded).values()):
                if isinstance(value, Foreign):
                    found[id(value)] = value
    for _, given in needed_by(service):
        found[id(given.foreign)] = given.foreign
    return list(found.values())


def needed_by(service: Service[Any]) -> list[tuple[str, Needs]]:
    """Every need a book states, with where: a journey's given and a step of a scene."""
    out: list[tuple[str, Needs]] = [(f"journey {journey.__name__}", given) for journey in service.journeys
                                    for given in journey.given if isinstance(given, Needs)]
    for axes in service.matrices:
        for scene in axes.scenes:
            try:
                out += [(f"scene {axes.record}:{scene.name}", step) for step in scene.reached_by(axes.today) if isinstance(step, Needs)]
            except Exception:
                continue
    return out


def walked(service: Service[Any]) -> list[tuple[type[Journey], object]]:
    """Every step the journeys take, built on a model with no send: a step the model carries is performed on it, as `exercised` does."""
    out: list[tuple[type[Journey], object]] = []
    for journey in service.journeys:
        try:
            model = given_model(service, journey)
            for step in journey().steps(model.today):
                step = step.step if isinstance(step, (Refused, OwnerRefused)) else step
                out.append((journey, step))
                if isinstance(step, Endpoint) and step.carries is not None:
                    try:
                        model.perform(step)
                    except Exception:
                        break
        except Exception:
            continue
    return out


def passed_on(service: Service[Any]) -> list[tuple[type[Endpoint], Any]]:
    """The call of another book each step that passes an answer on or reaches a call builds, once per endpoint and call class."""
    out: dict[tuple[type[Endpoint], type], tuple[type[Endpoint], Any]] = {}
    for _, step in walked(service):
        if not isinstance(step, Endpoint):
            continue
        endpoint = type(step)
        for build in (step.passes.asks if step.passes is not None else None, step.reaches.call if step.reaches is not None else None):
            if build is None:
                continue
            try:
                call = build(step)
            except Exception:
                continue
            out.setdefault((endpoint, type(call)), (endpoint, call))
    return list(out.values())


def answered(call: type[Endpoint]) -> set[str]:
    """The field names of the success answers of a call: the answer's object, or the entry's object of a list."""
    out: set[str] = set()
    for answer in call.answers:
        shape = answer.body.of if isinstance(answer.body, List) else answer.body
        if succeeded(answer.status) and isinstance(shape, Object):
            out |= set(shape.fields)
    return out


def stored(service: Service[Any]) -> set[str]:
    """The record names a book keeps: the entity class of each collection of its model and the records it lists."""
    names = {record.__name__ for record in service.records}
    try:
        collections = getattr(type(service.new_model(date.today())), "collections", None)
        names |= {c.of.__name__ for c in collections().values()} if collections is not None else set()
    except Exception:
        pass
    return names


def held_records(service: Service[Any]) -> set[str]:
    """The record names a book's model and matrices state: the entity class of each collection of the model, the label of each matrix, and the
    records the book lists. A record kept in a plain attribute, or in a collection of a state the model reaches only by `Become`, is not seen."""
    return {axes.record for axes in service.matrices} | stored(service)


def reference_faults(module: str, found: dict[str, Service[Any]], skipped: dict[str, str]) -> list[Finding]:
    """What a neighbour's reference to an owner says that the owner's book no longer answers, for the book `module` as neighbour or owner."""
    from ostler.book.owners import book_of

    refs = {name: references(name, book) for name, book in found.items()}
    out: list[Finding] = []
    for name, book in found.items():
        calls = passed_on(book) if any(e.passes is not None or e.reaches is not None for e in book.endpoints) else []
        for endpoint, call in calls:
            callee = book_of(call)
            if callee in found and type(call) not in found[callee].endpoints and module in (name, callee):
                out.append(Finding(f"endpoint {endpoint.__name__}", f"{name} passes on or reaches {type(call).__name__} of {callee}, and it is no endpoint "
                                   f"of {callee}'s book: it was removed or moved out of the service's endpoints"))
        for ref in refs[name]:
            owner, record = ref.owner, ref.record.__name__
            if module not in (name, owner):
                continue
            asked = {type(call) for _, call in calls if book_of(call) == owner}
            seen = set().union(*(answered(c) for c in asked)) if asked else set()
            where = ", ".join(sorted(c.__name__ for c in asked))
            out += [Finding(f"foreign {record}", f"{name} reads {field} of {record} of {owner}, and no success answer of {where} has it")
                    for field in ref.reads if asked and field not in seen]
            if not ref.named:
                continue
            if owner in found:
                out.append(Finding(f"foreign {record}", f"{name} names {record} by a word, and {owner} has a book: name the record class of that book"))
            elif owner not in skipped:
                out.append(Finding(f"foreign {record}", f"{name} names {record} by a word, and its owner {owner} has no book under the root yet", told=True))
        for where, given in needed_by(book):
            if given.foreign.owner not in found or module not in (name, given.foreign.owner):
                continue
            owner = given.foreign.owner
            states = list(dict.fromkeys(scene.name for axes in found[owner].matrices for scene in axes.scenes))
            if given.state not in states:
                out.append(Finding(where, f"{name} needs {given.foreign.record.__name__} of {owner} in "
                                   f"{given.state!r}, and no matrix of {owner} has that state: its states are {', '.join(states)}"))
            elif given.person is not None and given.person not in found[owner].cast:
                out.append(Finding(where, f"{name} needs {given.foreign.record.__name__} of {owner} for {given.person}, "
                                   f"who is not in the cast of {owner}: its cast is {', '.join(str(a) for a in found[owner].cast)}"))
            elif given.foreign.takes is not None:
                out += [f for f in view_faults(where, name, given, found[owner]) if f not in out]
    return out


def view_faults(where: str, name: str, given: Needs, owner: Service[Any]) -> list[Finding]:
    """The fields a screen reads of a needed record that the owner's view of it lacks."""
    from ostler.book.owners import Owners, shown_of

    try:
        owned, entity = Owners.alone(owner, given)
    except BookError as cannot:
        return [Finding(where, f"{name} needs {given.foreign.record.__name__} of {given.foreign.owner} in {given.state!r}, "
                        f"and the owner's book cannot arrange it alone: {cannot}")]
    shown = shown_of(owned.row(entity))
    return [Finding(f"foreign {given.foreign.record.__name__}", f"{name} reads {field} of {given.foreign.record.__name__} of "
                    f"{given.foreign.owner}, and the owner's view of it in {given.state!r} has no such field: it has {', '.join(shown)}")
            for field in given.foreign.reads if field not in shown]


def answers_calls(service: Service[Any]) -> bool:
    return not service.screens and any(environment.hosts for environment in service.environments.values())


def trespass_faults(module: str, service: Service[Any], found: dict[str, Service[Any]]) -> list[Finding]:
    """A record or a call of another book this book holds a life for. A record this book itself names as a `Foreign` and a call sent by
    a book that states a `Foreign` block. A record that only shares its name with another book's is a note and the check passes: two
    services may each store a record of that name, and a book written before a book could refer to another is not failed by it. A screen book keeps its own model of what its user sees, and a command book keeps the files
    its commands work on and names no host, so only a book that reaches a service by a host is compared with another."""
    if not answers_calls(service):
        return []
    foreign = {ref.record.__name__ for ref in references(module, service)}
    stated = bool(foreign)
    said = ("the book that does not store the record refers to it with Foreign and asks for a state with Needs, "
            "and the book that stores it arranges it")
    out: list[Finding] = []
    mine = held_records(service)
    for name, book in found.items():
        if name == module or not answers_calls(book):
            continue
        theirs = {ref.record.__name__ for ref in references(name, book) if ref.owner == module}
        out += [Finding(f"record {record}", f"{module} and {name} both hold {record}: if it is one record, {said}", told=record not in foreign)
                for record in sorted((mine & held_records(book)) - theirs)]
    sent: set[tuple[str, type]] = set()
    for journey, step in walked(service):
        if not isinstance(step, Endpoint) or type(step) in service.endpoints:
            continue
        for name, book in found.items():
            if name != module and type(step) in book.endpoints and (name, type(step)) not in sent:
                sent.add((name, type(step)))
                out.append(Finding(f"journey {journey.__name__}", f"{module} sends {type(step).__name__}, a call of {name}'s book: {said}", told=not stated))
    return out


def effects(before: Any, after: Any) -> tuple[set[str], set[str]]:
    """The records an act changed on a model, and the ones it made."""
    changed: set[str] = set()
    made: set[str] = set()
    for name in type(before).collections():
        old, new = getattr(before, name), getattr(after, name)
        if old.items != new.items:
            changed.add(new.of.__name__)
        if set(new.items) - set(old.items):
            made.add(new.of.__name__)
    return changed, made


def acted(service: Service[Any]) -> list[tuple[type[Interaction[Any]], set[str], set[str]]]:
    """Each interaction the book's scenes, cells and journeys take on the model alone, with the records it changed and made."""
    from ostler.book.owners import Owners

    out: list[tuple[type[Interaction[Any]], set[str], set[str]]] = []

    def take(step: object, model: Any) -> None:
        if not isinstance(step, Interaction):
            return
        before = model.copy()
        try:
            model.perform(step)
            out.append((type(step), *effects(before, model)))
        except Exception:
            return

    for axes in service.matrices:
        for scene in axes.scenes:
            try:
                model = service.new_model(axes.today)
                for step in scene.reached_by(axes.today):
                    if isinstance(step, Needs):
                        Owners.seed(step, model)
                    else:
                        take(step, model)
                for build in axes.actions.values():
                    take(build(model.copy()), model.copy())
            except Exception:
                continue
    for journey in service.journeys:
        try:
            model = given_model(service, journey)
            for step in journey().steps(model.today):
                take(step, model)
        except Exception:
            continue
    return out


def copy_faults(module: str, service: Service[Any], found: dict[str, Service[Any]]) -> list[Finding]:
    """A screen book keeps the life of a record only where one of its screens writes it, and makes no record outside its screens that a
    backend book under the root stores. The finding names the record and the owner's book. It blocks once the book refers to a foreign record;
    until then it is a note, so a book written before a book could refer to another still passes."""
    if not service.screens:
        return []
    backends = {name: book for name, book in found.items() if name != module and answers_calls(book)}
    if not backends:
        return []
    told = not references(module, service)
    owned = {name: stored(book) for name, book in backends.items()}
    written: set[str] = set()
    outside: dict[str, set[str]] = {}
    for act, changed, made in acted(service):
        if act.screen is not None:
            written |= changed
        elif made:
            outside.setdefault(act.__name__, set()).update(made)
    out: list[Finding] = []
    for record in sorted(stored(service) - written):
        owners = [name for name, names in owned.items() if record in names]
        if owners:
            out.append(Finding(f"record {record}", f"{module} keeps {record}, which no screen of it writes, and {', '.join(owners)} stores it: "
                               f"ask {owners[0]}'s book for the state with Needs and drop the lifecycle, rules and actions kept here", told=told))
    for name, made in sorted(outside.items()):
        for record in sorted(made):
            owners = [n for n, names in owned.items() if record in names] or list(backends)
            out.append(Finding(f"interaction {name}", f"{module} makes {record} outside its screens, and {', '.join(owners)} stores it: "
                               f"ask {owners[0]}'s book for the state with Needs instead of making the record here", told=told))
    return out


def boundary_faults(service: Service[Any], module: str) -> list[Finding]:
    """What this book's references to other books' records, or other books' references to its own, say that the other book no longer answers."""
    from ostler.book.eventmap import books

    found, skipped = books(module, service)
    out = [Finding(f"book {name}", f"cannot be loaded, so its boundary is not read: {why}", blocks=False) for name, why in skipped.items()]
    return out + reference_faults(module, found, skipped) + trespass_faults(module, service, found) + copy_faults(module, service, found)


def matrix_faults(service: Service[Any]) -> list[Finding]:
    """An endpoint no lifecycle matrix names has no record to scope its cells to,
    so the exploration plays it once in every state of every record."""
    named: set[type] = set()
    for axes in service.matrices:
        for build in axes.actions.values():
            for scene in axes.scenes:
                try:
                    call = build(scene.arrange(service.new_model(axes.today)))
                except Exception:
                    continue
                if call is not None and isinstance(call, Endpoint):
                    named.add(type(call))
                    break
    return [Finding(f"endpoint {e.__name__}", "no lifecycle matrix names it, so exploration plays it in every state of every record: give it a column in the matrix of the record it reads or writes")
            for e in service.endpoints if e not in named and e.passes is None and e.reaches is None and not e.streams]


def spoken(service: Service[Any]) -> list[Finding]:
    """Every label that misses a language the service declares or names one it does not, and every journey that plays in a language the service does not declare."""
    if not service.languages:
        if not service.screens:
            return []
        try:
            service.language
        except BookError as crash:
            return [Finding("service", str(crash))]
    declared = set(service.languages)
    listed = ", ".join(service.languages)
    found: list[Finding] = []
    for screen in service.screens:
        labelled = [] if isinstance(screen.name, Component) else [("name", as_label(screen.name))]
        if screen.root is not None:
            labelled.append(("root", screen.root.label))
        for attribute, value in vars(screen).items():
            if isinstance(value, Component):
                labelled.append((attribute, value.label))
                labelled += [(attribute, option) for option in value.options]
        for attribute, label in labelled:
            named = label.languages() if label is not None else None
            if label is None or named is None or named == declared:
                continue
            text = label.texts[0][1]
            where = f"screen {screen.__name__}.{attribute}"
            if declared - named:
                found.append(Finding(where, f"the label {text!r} has no text in {', '.join(sorted(declared - named))}"))
            if named - declared:
                found.append(Finding(where, f"the label {text!r} names {', '.join(sorted(named - declared))}, which the service does not declare; it declares {listed}"))
    for journey in service.journeys:
        if journey.lang and journey.lang not in declared:
            found.append(Finding(f"journey {journey.__name__}", f"plays in {journey.lang!r}, which the service does not declare; it declares {listed}"))
    return found


def name_faults(service: Service[Any]) -> list[Finding]:
    """Every screen whose `name`, the screen's own name, holds a component."""
    return [Finding(f"screen {screen.__name__}.name", "`name` is the screen's own name, and here it holds a component; give the component another attribute name")
            for screen in service.screens if isinstance(screen.name, Component)]


def shape_faults(service: Service[Any]) -> list[Finding]:
    """Every component a person fills that states nothing a run could try: a field, text area or date with no shape, and a
    select with no shape, no options and no list."""
    found: list[Finding] = []
    for screen in service.screens:
        for attribute, component in screen.attributes():
            where = f"screen {screen.__name__}.{attribute}"
            if component.kind in ("field", "textarea", "date") and component.holds is None:
                found.append(Finding(where, "a person fills it and it states no shape, so no input is tried on it: give it takes= and holds="))
            elif component.kind == "select" and component.holds is None and not component.options and component.lists is None:
                found.append(Finding(where, "a person picks in it and it states neither its options, what its list holds, nor a shape"))
    return found


def body_faults(service: Service[Any]) -> list[Finding]:
    """Every request body field of text that states no length, format or samples, so no input could be tried on it."""
    return [Finding(f"endpoint {endpoint.__name__}.{name}", "the field states no length, no format, no set of values and no samples, so no input can be "
                    "tried on it: state what the app enforces with max_len=, format= or an Enum, and where it enforces nothing give classes= "
                    "with the samples the play sends")
            for endpoint in service.endpoints for name, spec in body_fields(endpoint)
            if isinstance(spec.shape, Str) and not states_shape(spec)]


def fill_faults(service: Service[Any]) -> list[Finding]:
    """Every component that states a shape on a screen where no interaction of the book fills it."""
    found: list[Finding] = []
    for screen in service.screens:
        filled = {id(c) for i in service.interactions if i.screen is screen for c in i.typed()}
        for attribute, component in screen.attributes():
            if component.holds is not None and id(component) not in filled:
                found.append(Finding(f"screen {screen.__name__}.{attribute}", "it states a shape and no interaction of the book fills it, "
                                     f"so no input is tried on it: give an interaction of this screen a fixture that has {component.takes}",
                                     blocks=False))
    return found


def unstated_lists(service: Service[Any]) -> list[Finding]:
    """Every select that states a shape and neither its options nor what its list holds."""
    return [Finding(f"screen {screen.__name__}.{attribute}", "nothing states what its list holds: give it options=(...) or lists=Lists(...)", told=True)
            for screen in service.screens for attribute, component in screen.attributes()
            if component.kind == "select" and component.holds is not None and not component.options and component.lists is None]


def check(service: Service[Any], module: str, app: str | None = None) -> list[Finding]:
    found: list[Finding] = spoken(service)
    today = date.today()
    for endpoint in service.endpoints:
        attempt(found, f"endpoint {endpoint.__name__}", endpoint.describe, required=True)
        attempt(found, f"endpoint {endpoint.__name__} does", lambda e=endpoint: e.does, required=True)
    for screen in service.screens:
        for lang in service.languages:
            attempt(found, f"screen {screen.__name__} ({lang})", lambda s=screen, g=lang: s.describe(g), required=True)
    for interaction in service.interactions:
        attempt(found, f"interaction {interaction.__name__}", interaction.describe, required=True)
        attempt(found, f"interaction {interaction.__name__} does", lambda i=interaction: i.does, required=True)
    for journey in service.journeys:
        attempt(found, f"journey {journey.__name__} title", journey.title, required=True)
        attempt(found, f"journey {journey.__name__} story", journey.story, required=True)
    for axes in service.matrices:
        if axes.state_of is None:
            found.append(Finding(f"matrix {axes.record}", "declares no state_of, so exploration cannot tell its states apart"))
        else:
            attempt(found, f"state_of {axes.record}", lambda a=axes: a.states(service.new_model(a.today)))
        for scene in axes.scenes:
            attempt(found, f"scene {axes.record}:{scene.name}", lambda a=axes, s=scene: s.describe(a.today), required=True)
            for name, build in axes.actions.items():
                def one(a=axes, s=scene, n=name, b=build) -> str:
                    model = s.arrange(service.new_model(a.today))
                    action = b(model)
                    if action is None:
                        raise BookError("builds None where the pair is impossible: give Impossible(why)")
                    if isinstance(action, Impossible):
                        return f"impossible: {action.why}"
                    return str(cell(s.name, n, model, action, a.told_apart))

                attempt(found, f"cell {axes.record}:{scene.name} x {name}", one, required=True)
        attempt(found, f"matrix {axes.record}", lambda a=axes: matrix(service.new_model, a), required=True)
        attempt(found, f"graph {axes.record}", lambda a=axes: dot(service.new_model, a), required=True)
    for event in service.outside:
        accept = event.carries.accept if event.carries is not None else None
        if not _overrides(accept):
            found.append(Finding(f"outside {event.__name__}", "its fixture gives no examples, so exploration cannot aim it: "
                                 "give the fixture `examples`"))
    attempt(found, "search index", lambda: items(service, module), required=True)
    attempt(found, "model", lambda: service.new_model(today).describe(), required=True)
    if service.endpoints:
        attempt(found, "plan moves", lambda: moves(service.endpoints, cast=service.cast)(service.new_model(today)))
        attempt(found, "denied attempts", lambda: attempts(service.endpoints, service.new_model(today), cast=service.cast))
    attempt(found, "identities", lambda: found.extend(identity_faults(service)) or "done")
    attempt(found, "defects", lambda: found.extend(defect_faults(service)) or "done")
    attempt(found, "itself", lambda: found.extend(itself_faults(service)) or "done")
    attempt(found, "headers", lambda: found.extend(header_faults(service)) or "done")
    attempt(found, "clock", lambda: found.extend(clock_faults(service)) or "done")
    attempt(found, "input classes", lambda: found.extend(input_faults(service)) or "done")
    attempt(found, "screen names", lambda: found.extend(name_faults(service)) or "done")
    attempt(found, "screen shapes", lambda: found.extend(shape_faults(service)) or "done")
    attempt(found, "body shapes", lambda: found.extend(body_faults(service)) or "done")
    attempt(found, "unstated lists", lambda: found.extend(unstated_lists(service)) or "done")
    attempt(found, "screen fills", lambda: found.extend(fill_faults(service)) or "done")
    attempt(found, "sources", lambda: found.extend(source_faults(service, app)) or "done")
    attempt(found, "decisions", lambda: found.extend(decision_faults(service, module, app)) or "done")
    attempt(found, "questions", lambda: found.extend(question_faults(service, module)) or "done")
    attempt(found, "registration", lambda: found.extend(registration_faults(service, module)) or "done")
    attempt(found, "matrices", lambda: found.extend(matrix_faults(service)) or "done")
    attempt(found, "events", lambda: found.extend(event_faults(service, module)) or "done")
    attempt(found, "boundary", lambda: found.extend(f for f in boundary_faults(service, module) if f not in found) or "done")
    return found


def report(found: list[Finding]) -> None:
    for finding in found:
        print(f"{'NOTE ' if finding.told else 'CHECK'}  {finding}")
    failing, notes = sum(not f.told for f in found), sum(f.told for f in found)
    print(f"check: {failing} finding{'s' if failing != 1 else ''}" + (f", {notes} note{'s' if notes != 1 else ''}" if notes else ""))


def broken(service: Service[Any], module: str) -> bool:
    """Prints the findings and says whether the book must not run."""
    found = check(service, module)
    if found:
        report(found)
    return any(f.blocks for f in found)


def index_faults(service: Service[Any], module: str) -> list[Finding]:
    from ostler.book.index import write

    path, changed = write(service, module)
    return [Finding("index", "index differed from the committed one", blocks=False)] if changed else []


def secret_faults(service: Service[Any], name: str | None) -> list[Finding]:
    """Every secret the environment names must be registered in saddlebag, which `list` shows by name alone."""
    environment = service.environment(name)
    if not environment.secrets:
        return []
    done = subprocess.run(["saddlebag", "list"], capture_output=True, text=True, check=False)
    if done.returncode:
        return [Finding("secrets", f"saddlebag list failed: {(done.stderr or done.stdout).strip()}", blocks=False)]
    known = {line.split()[0] for line in done.stdout.splitlines()[1:] if line.split()}
    return [Finding("secrets", f"{secret} (the password of {handle} in {environment.name}) is not in saddlebag list", blocks=False)
            for handle, secret in environment.secrets.items() if secret not in known]


def cmd_check(service: Service[Any], args: argparse.Namespace) -> int:
    indexed: list[Finding] = []
    attempt(indexed, "index", lambda: indexed.extend(index_faults(service, args.service)) or "done")
    found = check(service, args.service, args.app)
    attempt(found, "secrets", lambda: found.extend(secret_faults(service, args.env)) or "done")
    found.extend(indexed)
    report(found)
    return 1 if any(not f.told for f in found) else 0
