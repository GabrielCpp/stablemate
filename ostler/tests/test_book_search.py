"""`ostler book search` over a service held in memory: which lines of which items a term reaches."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ostler.book import Answer, Endpoint, Screen, T
from ostler.book.screen import Button
from ostler.book.domain import State
from ostler.book.search import items, search

from test_book_web import _service


class Greeting(Screen):
    name = T(fr="Accueil", es="Inicio")
    go = Button(None, T(fr="Aller", es="Ir"))
    save = Button(None, T(fr="Enregistrer", es="Guardar"))
    source = ("web/greeting.tsx::Greeting",)


class Plain(Screen):
    name = "Settings"
    save = Button(None, "Save")


class Ping(Endpoint):
    path = "/ping"
    answers = (Answer(200, None, "pong"),)
    source = ("api/handlers/ping.py::ping",)
    does = "Answers pong."


class Silent(Endpoint):
    path = "/silent"
    answers = (Answer(200, None, "quiet"),)


def _book(*screens: type[Screen], endpoints: tuple[type[Endpoint], ...] = (), languages: tuple[str, ...] = ("fr",)) -> Any:
    return replace(_service(*screens, languages=languages), new_model=State, endpoints=endpoints)


def _found(service: Any, term: str, kind: str | None = None, mod: str = "shop_book") -> list[str]:
    return [item.name for item, _ in search(service, mod, term, kind)]


def test_a_label_in_the_second_language_of_the_book_finds_its_screen(module: str):
    service = _book(Greeting, languages=("fr", "es"))
    assert _found(service, "Guardar", mod=module) == ["Greeting"]


def test_the_items_of_a_one_language_book_are_the_lines_of_its_first_language(module: str):
    service = _book(Plain, languages=("en",))
    [screen] = [item for item in items(service, module) if item.kind == "screen"]
    assert screen.lines == tuple(Plain.describe("en").splitlines())


def test_a_source_file_name_finds_the_screen_written_from_it(module: str):
    service = _book(Greeting, Plain, languages=("fr",))
    assert _found(service, "greeting.tsx", mod=module) == ["Greeting"]


def test_a_part_of_a_source_path_finds_the_endpoint_written_from_it(module: str):
    service = _book(endpoints=(Ping, Silent))
    assert _found(service, "api/handlers", mod=module) == ["Ping"]


def test_an_element_with_no_source_has_no_source_line(module: str):
    service = _book(endpoints=(Silent,))
    [endpoint] = [item for item in items(service, module) if item.kind == "endpoint"]
    assert not [line for line in endpoint.lines if line.startswith("source:")]
