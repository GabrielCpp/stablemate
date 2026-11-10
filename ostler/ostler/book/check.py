"""The book checked before it runs: everything the commands build from the
declarations is built once, with no stack, and anything that raises or comes
out without its text is a finding that names the object."""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterator, cast

from ostler.book import decisions
from ostler.book.arrange import Arrange
from ostler.book.explore import _overrides, attempts, moves
from ostler.book.graph import dot
from ostler.book.http import Endpoint, bare_ids
from ostler.book.journey import Journey
from ostler.book.model import Rule
from ostler.book.inputs import bases, classes, expected, has_inputs, predicted, refusals_for, vary
from ostler.book.errors import BookError
from ostler.book.matrix import cell, matrix
from ostler.book.state import Impossible
from ostler.book.outcome import Done
from ostler.book.status import succeeded
from ostler.book.search import actions_of, items, states_of
from ostler.book.service import Service
from ostler.book.sources import missing


@dataclass(frozen=True)
class Finding:
    name: str
    problem: str
    blocks: bool = True

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


def exercised(service: Service[Any]) -> Iterator[tuple[str, Any, list[str], Any]]:
    """Every endpoint call the journeys make, replayed on the model alone: where
    it is, the call, the ids it sends where another kind is typed, and what the
    model answered."""
    for journey in service.journeys:
        model = service.new_model(date.today())
        for given in journey.given:
            model.perform(given.request)
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


def input_faults(service: Service[Any]) -> list[Finding]:
    found: list[Finding] = []
    skipped = {u.endpoint for u in service.unseen if u.item == "inputs"}
    reached = bases(service)
    labels: dict[type[Endpoint], set[str]] = {}
    for endpoint in service.endpoints:
        if endpoint.carries is None or not has_inputs(endpoint):
            continue
        name = f"endpoint {endpoint.__name__}"
        base = reached.get(endpoint)
        if endpoint in skipped:
            if base is not None:
                found.append(Finding(name, "inputs are declared unseen, but a step reaches it: delete the declaration"))
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
            if not expected(c, predicted(call, base.before)) and not declared and refusals_for(service, endpoint).of(c.default) is None:
                found.append(Finding(name, f"{c.label}: the model has no rule and the book declares no {c.default} refusal"))
    for d in service.diverges:
        if d.label not in labels.get(d.endpoint, set()):
            found.append(Finding(f"diverges {d}", "no input class of the endpoint has this label"))
    return found


def source_faults(service: Service[Any], app: str | None) -> list[Finding]:
    found = [Finding(e.__name__, "no source pointer", blocks=False) for e in (*service.endpoints, *service.records) if not cast(Any, e).source]
    if app is not None:
        found += [Finding(name, f"source {path} does not exist under {app}") for name, path in missing(service, app)]
    return found


def decision_faults(service: Service[Any], module: str) -> list[Finding]:
    found: list[Finding] = []
    known = decisions.resolve(service, module)
    for d in decisions.load(module):
        name = f"decision {d.slug}"
        if not d.story:
            found.append(Finding(name, "no story", blocks=False))
        if not d.date:
            found.append(Finding(name, "no date", blocks=False))
        if not d.elements:
            found.append(Finding(name, "names no element", blocks=False))
        found += [Finding(name, f"element {e} resolves to no endpoint, record or model name", blocks=False)
                  for e in d.elements if e not in known]
    return found


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
    stepped = tuple({type(step) for journey in service.journeys for step in journey().steps(date.today()) if isinstance(step, Arrange)})
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
            for e in service.endpoints if e not in named]


def check(service: Service[Any], module: str, app: str | None = None) -> list[Finding]:
    found: list[Finding] = []
    today = date.today()
    for endpoint in service.endpoints:
        attempt(found, f"endpoint {endpoint.__name__}", endpoint.describe, required=True)
        attempt(found, f"endpoint {endpoint.__name__} does", lambda e=endpoint: e.does, required=True)
    for screen in service.screens:
        for lang in ("en", "fr"):
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
    attempt(found, "headers", lambda: found.extend(header_faults(service)) or "done")
    attempt(found, "input classes", lambda: found.extend(input_faults(service)) or "done")
    attempt(found, "sources", lambda: found.extend(source_faults(service, app)) or "done")
    attempt(found, "decisions", lambda: found.extend(decision_faults(service, module)) or "done")
    attempt(found, "registration", lambda: found.extend(registration_faults(service, module)) or "done")
    attempt(found, "matrices", lambda: found.extend(matrix_faults(service)) or "done")
    return found


def report(found: list[Finding]) -> None:
    for finding in found:
        print(f"CHECK  {finding}")
    print(f"check: {len(found)} finding{'s' if len(found) != 1 else ''}")


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
    found = check(service, args.service, args.app)
    attempt(found, "secrets", lambda: found.extend(secret_faults(service, args.env)) or "done")
    attempt(found, "index", lambda: found.extend(index_faults(service, args.service)) or "done")
    report(found)
    return 1 if found else 0
