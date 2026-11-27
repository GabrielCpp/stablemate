"""Ask a book what it says, in words: `search` finds every place a term
appears among the endpoints, rules, actions, journeys, screens and scenes, and
`explain` prints everything the book knows of one named class."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

from ostler.book import decisions, questions
from ostler.book.arrange import Arrange
from ostler.book.domain import Action, State
from ostler.book.entries import says
from ostler.book.errors import BookError
from ostler.book.event import Event
from ostler.book.http import identity_lines
from ostler.book.model import Defect, Rule
from ostler.book.reach import described, reach_line, route_text
from ostler.book.screen import Component, Interaction, Screen
from ostler.book.service import Service
from ostler import textrows
from ostler.textrows import BOOK_KINDS

KINDS = BOOK_KINDS


@dataclass(frozen=True)
class Item:
    kind: str
    address: str
    name: str
    lines: tuple[str, ...]
    reach: str = ""


def address(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def subclasses[T](cls: type[T]) -> Iterator[type[T]]:
    for sub in cls.__subclasses__():
        yield sub
        yield from subclasses(sub)


def replaced(cls: type) -> bool:
    """Whether the module of `cls` now holds another class under its name: `cls` was left by an earlier import of the book."""
    if "<locals>" in cls.__qualname__ or cls.__module__ not in sys.modules:
        return False
    held: object = sys.modules[cls.__module__]
    for part in cls.__qualname__.split("."):
        held = getattr(held, part, None)
    return held is not None and held is not cls


def actions_of(service: Service[Any], module: str) -> list[type[Action[Any, Any]]]:
    found: dict[type[Action[Any, Any]], None] = {}
    for endpoint in service.endpoints:
        if endpoint.carries is not None:
            found[endpoint.carries] = None
    for interaction in service.interactions:
        if interaction.carries is not None:
            found[interaction.carries] = None
    for sub in subclasses(Action):
        if sub.__module__.startswith(module) and not replaced(sub):
            found[sub] = None
    return list(found)


def states_of(service: Service[Any]) -> list[type[State]]:
    kind = type(service.new_model(date.today()))
    root = next((c for c in kind.__mro__ if State in c.__bases__), kind)
    return [root, *subclasses(root)]


def rule_lines(rule: Rule[Any, Any]) -> tuple[str, ...]:
    return (f"{rule.status} {rule.message}", *((f"why: {rule.why}",) if rule.why else ()))


def defect_lines(defect: Defect[Any, Any]) -> tuple[str, ...]:
    head = f"breaks {says(defect.breaks)}: {defect.message}" if defect.breaks is not None else f"{defect.status} {defect.message}"
    return (head, *((f"why: {defect.why}",) if defect.why else ()))


def source_lines(element: Any) -> tuple[str, ...]:
    return tuple(f"source: {pointer}" for pointer in element.source)


def event_lines(event: type[Event]) -> tuple[str, ...]:
    summary = (event.__doc__ or "").strip().splitlines()[0]
    fields = event.detail.fields.items() if event.detail is not None else ()
    return (event.name, *((f"source: {event.source}",) if event.source else ()), summary,
            *(f"{key}: {spec.shape.describe()}" for key, spec in fields),
            *((f"owner: {event.owner}",) if event.owner else ()))


def outside_lines(outside: type[Arrange[Any]]) -> tuple[str, ...]:
    return (outside.does, *((f"carries: {outside.carries.__name__}",) if outside.carries is not None else ()),
            *((f"heard: {outside.heard.name}",) if outside.heard is not None else ()),
            *(f"reads: {path}" for path in outside.reads))


def screen_lines(service: Service[Any], screen: type[Screen]) -> tuple[str, ...]:
    lines = described(service, screen, service.language).splitlines()
    sourced = source_lines(screen)
    seen = set(lines)
    for language in service.languages[1:]:
        for line in described(service, screen, language).splitlines():
            if line not in seen:
                seen.add(line)
                lines.append(line)
    return (*lines, *sourced)


def component_lines(service: Service[Any], attribute: str, component: Component) -> tuple[str, ...]:
    label = component.label
    named = label.languages() if label is not None else None
    labels = [] if label is None else [f"{lang}: {label[lang]}" for lang in service.languages if named is None or lang in named]
    return (f"{attribute}: {component.kind} {component.found_by(service.language)}", *labels, *((component.does,) if component.does else ()))


def items(service: Service[Any], module: str) -> list[Item]:
    out: list[Item] = []
    for endpoint in service.endpoints:
        out.append(Item("endpoint", address(endpoint), endpoint.__name__, (*endpoint.describe().splitlines(), *source_lines(endpoint))))
    for interaction in service.interactions:
        out.append(Item("interaction", address(interaction), interaction.__name__, (" ".join(interaction.describe().split()), *source_lines(interaction)),
                        reach_line(service, interaction.screen) if interaction.screen is not None else ""))
    for action in actions_of(service, module):
        doc = tuple((action.__doc__ or "").strip().splitlines())
        out.append(Item("action", address(action), action.__name__, (action.__name__, *doc, *((f"clock: {action.clock}",) if action.clock else ()), *(f"emits: {e.name}" for e in action.emits))))
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
        out.append(Item("screen", address(screen), screen.__name__, screen_lines(service, screen), reach_line(service, screen)))
        for attribute, component in screen.attributes():
            out.append(Item("component", f"{address(screen)}.{attribute}", f"{screen.__name__}.{attribute}",
                            component_lines(service, attribute, component), reach_line(service, screen)))
    for axes in service.matrices:
        for scene in axes.scenes:
            out.append(Item("scene", f"{axes.record}:{scene.name}", scene.name, (scene.describe(axes.today),)))
    for event in service.events:
        out.append(Item("event", address(event), event.__name__, event_lines(event)))
    for outside in service.outside:
        out.append(Item("outside", address(outside), outside.__name__, outside_lines(outside)))
    for decision in decisions.load(module):
        for number, text in decision.searchable():
            out.append(Item("decision", f"decisions/{decision.slug}.md:{number}", decision.slug, (text,)))
    for question in questions.load(module):
        out.append(Item("question", f"QUESTIONS.md:{question.line}", question.element, (f"{question.element}: {question.text}",)))
    return out


SERVICE_LIMIT = 50


def search(service: Service[Any], module: str, term: str, kind: str | None = None) -> list[dict]:
    """The ranked hits of `term` among the elements of one loaded book, by the engine `ostler search` uses."""
    from ostler import textindex

    rows = textrows.book_rows(module, items(service, module))
    return textindex.search_rows(rows, term, etype=kind, root=textrows.BOOKS, limit=SERVICE_LIMIT)


def cmd_search(service: Service[Any], args: Any) -> int:
    from ostler import textindex

    hits = search(service, args.service, args.term, args.kind)
    for line in textindex.render(hits):
        print(line)
    if not hits:
        print(f"nothing in {service.name} says {args.term!r}" + (f" as a {args.kind}" if args.kind else ""))
    return 0 if hits else 1


def journeys_naming(service: Service[Any], cls: type) -> list[type]:
    return [j for j in service.journeys if getattr(sys.modules.get(j.__module__), cls.__name__, None) is cls]


def cmd_explain(service: Service[Any], args: Any) -> int:
    if "." in args.name:
        return _explain_component(service, args)
    known = [*service.endpoints, *actions_of(service, args.service), *service.screens, *service.journeys, *service.interactions]
    found = [c for c in known if c.__name__ == args.name] or [e for e in service.events if e.__name__ == args.name]
    if not found:
        raise SystemExit(f"nothing in {service.name} is called {args.name!r}; try `search {args.service} {args.name}`")
    cls: Any = found[0]
    print(address(cls))
    if cls in service.endpoints:
        print(cls.describe())
        print("\n".join(identity_lines(service.endpoints, cls)))
        _print_list("journeys that call it", [j.__name__ for j in journeys_naming(service, cls)])
    elif cls in service.screens:
        _explain_screen(service, cls)
    elif cls in service.journeys:
        print(cls.story())
        for given in cls.given:
            print(f"given: {given}")
    elif issubclass(cls, Event):
        _explain_event(service, args.service, cls)
    elif cls in service.interactions:
        print(cls.describe())
        _explain_moves(service, cls)
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
    asked = [q for q in questions.load(args.service) if q.element == args.name]
    if asked:
        print("\nOpen questions")
        for q in asked:
            print(f"- {q.text}")
    return 0


def _explain_screen(service: Service[Any], screen: type[Screen]) -> None:
    print(described(service, screen, service.language))
    print(reach_line(service, screen) if screen.inside is not None else f"from an entry: {route_text(service, screen)}")
    if screen.inside is not None and screen.shown_in is not None:
        print(f"{screen.inside.__name__} moves into {screen.shown_in.name}:")
        for transition in screen.inside.transitions:
            if transition.end is screen.shown_in:
                print(f"    {transition.text(service.language)}")


def _explain_moves(service: Service[Any], interaction: type[Interaction[Any]]) -> None:
    if interaction.screen is None:
        if interaction.leads_to is not None:
            print(f"leads to: {interaction.leads_to.__name__}")
        return
    print(f"from an entry: {route_text(service, interaction.screen)}")
    print(f"leads to: {interaction.leads_to.__name__}" if interaction.leads_to is not None else f"stays on {interaction.screen.__name__}")


def _explain_component(service: Service[Any], args: Any) -> int:
    owner, _, attribute = args.name.partition(".")
    screens = [s for s in service.screens if s.__name__ == owner]
    held = dict(screens[0].attributes()) if screens else {}
    if attribute not in held:
        raise SystemExit(f"nothing in {service.name} is called {args.name!r}; try `search {args.service} {attribute}`")
    screen, component = screens[0], held[attribute]
    print(f"{address(screen)}.{attribute}")
    print(component.describe(service.language))
    for phase in screen.phases:
        for how, members in (("shows", phase.shows), ("hides", phase.hides), ("disabled", phase.disabled),
                             ("states", tuple(s.component for s in phase.states))):
            if component in members:
                print(f"phase {phase.name}: {how}" + (f", because {phase.because}" if phase.because else ""))
    print(reach_line(service, screen))
    return 0


def _explain_event(service: Service[Any], module: str, event: type[Event]) -> None:
    from ostler.book.eventmap import books, emitters, hearers

    print("\n".join(event_lines(event)))
    emitting = emitters({module: service}, event)
    found, _ = books(module, service)
    listening = hearers(found, event)
    print("emitted by")
    for name, action in emitting:
        print(f"    {name}.{action.__name__}: {_first(action.__doc__)}")
    print("heard by")
    for name, outside in listening:
        print(f"    {name}.{outside.__name__}: {outside.does}")


def _first(doc: str | None) -> str:
    lines = (doc or "").strip().splitlines()
    return lines[0] if lines else ""


def _print_list(title: str, names: list[str]) -> None:
    if names:
        print(f"{title}: " + ", ".join(names))


__all__ = ["BookError", "KINDS", "cmd_explain", "cmd_search", "items", "search"]
