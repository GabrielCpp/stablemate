"""Ask a book what it says, in words: `search` finds every place a term
appears among the endpoints, rules, actions, journeys, screens and scenes, and
`explain` prints everything the book knows of one named class."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

from ostler.book import decisions
from ostler.book.domain import Action, State
from ostler.book.errors import BookError
from ostler.book.http import identity_lines
from ostler.book.model import Defect, Rule
from ostler.book.service import Service

KINDS = ("rule", "defect", "endpoint", "action", "journey", "screen", "scene", "decision")


@dataclass(frozen=True)
class Item:
    kind: str
    address: str
    name: str
    lines: tuple[str, ...]


def address(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def subclasses[T](cls: type[T]) -> Iterator[type[T]]:
    for sub in cls.__subclasses__():
        yield sub
        yield from subclasses(sub)


def actions_of(service: Service[Any], module: str) -> list[type[Action[Any, Any]]]:
    found: dict[type[Action[Any, Any]], None] = {}
    for endpoint in service.endpoints:
        if endpoint.carries is not None:
            found[endpoint.carries] = None
    for interaction in service.interactions:
        if interaction.carries is not None:
            found[interaction.carries] = None
    for sub in subclasses(Action):
        if sub.__module__.startswith(module):
            found[sub] = None
    return list(found)


def states_of(service: Service[Any]) -> list[type[State]]:
    kind = type(service.new_model(date.today()))
    root = next((c for c in kind.__mro__ if State in c.__bases__), kind)
    return [root, *subclasses(root)]


def rule_lines(rule: Rule[Any, Any]) -> tuple[str, ...]:
    return (f"{rule.status} {rule.message}", *((f"why: {rule.why}",) if rule.why else ()))


def defect_lines(defect: Defect[Any, Any]) -> tuple[str, ...]:
    return (f"{defect.status} {defect.message}", *((f"why: {defect.why}",) if defect.why else ()))


def items(service: Service[Any], module: str) -> list[Item]:
    out: list[Item] = []
    for endpoint in service.endpoints:
        out.append(Item("endpoint", address(endpoint), endpoint.__name__, tuple(endpoint.describe().splitlines())))
    for action in actions_of(service, module):
        doc = tuple((action.__doc__ or "").strip().splitlines())
        out.append(Item("action", address(action), action.__name__, (action.__name__, *doc)))
        for rule in action.rules:
            out.append(Item("rule", address(action), action.__name__, rule_lines(rule)))
        for defect in action.defects:
            out.append(Item("defect", address(action), action.__name__, defect_lines(defect)))
    for state in states_of(service):
        for rule in state.rules:
            out.append(Item("rule", address(state), state.__name__, rule_lines(rule)))
    for journey in service.journeys:
        out.append(Item("journey", address(journey), journey.__name__, (journey.__name__, *journey.story().splitlines())))
    for screen in service.screens:
        out.append(Item("screen", address(screen), screen.__name__, tuple(screen.describe("en").splitlines())))
    for axes in service.matrices:
        for scene in axes.scenes:
            out.append(Item("scene", f"{axes.record}:{scene.name}", scene.name, (scene.describe(axes.today),)))
    for decision in decisions.load(module):
        for number, text in decision.lines():
            out.append(Item("decision", f"decisions/{decision.slug}.md:{number}", decision.slug, (text,)))
    return out


def search(service: Service[Any], module: str, term: str, kind: str | None = None) -> list[tuple[Item, list[str]]]:
    wanted = term.lower()
    hits = []
    for item in items(service, module):
        if kind is not None and item.kind != kind:
            continue
        lines = [line.strip() for line in item.lines if wanted in line.lower()]
        if lines:
            hits.append((item, lines))
    return hits


def cmd_search(service: Service[Any], args: Any) -> int:
    hits = search(service, args.service, args.term, args.kind)
    for item, lines in hits:
        print(f"{item.kind:9} {item.address}")
        for line in lines:
            print(f"    {line}")
    if not hits:
        print(f"nothing in {service.name} says {args.term!r}" + (f" as a {args.kind}" if args.kind else ""))
    return 0 if hits else 1


def journeys_naming(service: Service[Any], cls: type) -> list[type]:
    return [j for j in service.journeys if getattr(sys.modules.get(j.__module__), cls.__name__, None) is cls]


def cmd_explain(service: Service[Any], args: Any) -> int:
    known = [*service.endpoints, *actions_of(service, args.service), *service.screens, *service.journeys, *service.interactions]
    found = [c for c in known if c.__name__ == args.name]
    if not found:
        raise SystemExit(f"nothing in {service.name} is called {args.name!r}; try `search {args.service} {args.name}`")
    cls: Any = found[0]
    print(address(cls))
    if cls in service.endpoints:
        print(cls.describe())
        print("\n".join(identity_lines(service.endpoints, cls)))
        _print_list("journeys that call it", [j.__name__ for j in journeys_naming(service, cls)])
    elif cls in service.screens:
        print(cls.describe("en"))
    elif cls in service.journeys:
        print(cls.story())
        for given in cls.given:
            print(f"given: {given}")
    elif cls in service.interactions:
        print(cls.describe())
        if cls.carries is not None:
            print(cls.carries.explain())
        _print_list("journeys that call it", [j.__name__ for j in journeys_naming(service, cls)])
    else:
        print(cls.explain())
        _print_list("carried by", [e.__name__ for e in (*service.endpoints, *service.interactions) if e.carries is cls])
        _print_list("journeys that call it", sorted({j.__name__ for e in (*service.endpoints, *service.interactions)
                                                      if e.carries is cls for j in journeys_naming(service, e)}))
    named = decisions.naming(decisions.load(args.service), args.name)
    if named:
        print("\nDecisions")
        for d in named:
            print(d.line())
    return 0


def _print_list(title: str, names: list[str]) -> None:
    if names:
        print(f"{title}: " + ", ".join(names))


__all__ = ["BookError", "KINDS", "cmd_explain", "cmd_search", "items", "search"]
