"""`ostler book search` over a service held in memory: which lines of which items a term reaches."""

from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from ostler.book import Answer, Endpoint, Screen, T
from ostler.book.screen import Button
from ostler.book import decisions
from ostler.book.domain import State
from ostler.book.search import cmd_search, items, search

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


class Editor(Screen):
    name = "Editor"
    commit = Button(None, "Save changes")


class Store(Endpoint):
    path = "/store"
    answers = (Answer(200, None, "stored"),)
    does = "Saves the settings."


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


def test_two_words_that_sit_apart_on_one_screen_find_it_when_no_phrase_matches(module: str):
    service = _book(Greeting, Plain, languages=("fr", "es"))
    assert _found(service, "enregistrer aller", mod=module) == ["Greeting"]


def test_a_phrase_that_matches_keeps_its_result_and_adds_no_loose_match(module: str):
    service = _book(Editor, Plain, languages=("en",))
    assert _found(service, "save changes", mod=module) == ["Editor"]


def test_loose_words_that_are_not_all_on_one_item_find_nothing_and_exit_one(module: str, capsys):
    service = _book(Greeting, Plain, languages=("fr",))
    args = SimpleNamespace(service=module, term="aller settings", kind=None)
    assert cmd_search(service, args) == 1
    assert capsys.readouterr().out == "nothing in mini says 'aller settings'\n"


def test_kind_narrows_a_loose_match(module: str):
    service = _book(Plain, endpoints=(Store,), languages=("en",))
    assert sorted(_found(service, "save settings", mod=module)) == ["Plain", "Store"]
    assert _found(service, "save settings", "endpoint", module) == ["Store"]
    assert _found(service, "save settings", "screen", module) == ["Plain"]


def test_a_loose_match_prints_only_the_lines_that_hold_a_word(module: str, capsys):
    service = _book(Greeting, languages=("fr", "es"))
    args = SimpleNamespace(service=module, term="enregistrer aller", kind=None)
    assert cmd_search(service, args) == 0
    printed = [line.strip() for line in capsys.readouterr().out.splitlines()[1:]]
    assert printed and all("aller" in line.lower() or "enregistrer" in line.lower() for line in printed)


def _decided(module: str) -> None:
    folder = decisions.directory(module)
    with open(os.path.join(folder, "refund.md"), "w") as f:
        f.write("story: SHOP-42\ndate: 2026-11-14\nelements: Checkout, Cart\nsources: app.py::refund\n\nA refund keeps the basket.\n")


def test_a_story_id_finds_its_decision(module: str):
    _decided(module)
    [(item, lines)] = search(_book(languages=("en",)), module, "SHOP-42", "decision")
    assert (item.kind, item.address, lines) == ("decision", "decisions/refund.md:1", ["story: SHOP-42"])


def test_a_class_name_finds_the_decision_that_explains_it(module: str):
    _decided(module)
    [(item, lines)] = search(_book(languages=("en",)), module, "Cart", "decision")
    assert (item.address, lines) == ("decisions/refund.md:3", ["elements: Checkout, Cart"])


def test_a_cited_source_finds_its_decision(module: str):
    _decided(module)
    [(item, lines)] = search(_book(languages=("en",)), module, "app.py::refund", "decision")
    assert (item.address, lines) == ("decisions/refund.md:4", ["sources: app.py::refund"])


def test_a_word_of_an_open_question_finds_it(module: str):
    questions = os.path.join(os.path.dirname(decisions.directory(module)), "QUESTIONS.md")
    with open(questions, "w") as f:
        f.write("# Open\n\n- Checkout: why does a refund wait a day?\n")
    [(item, lines)] = search(_book(languages=("en",)), module, "refund wait", "question")
    assert (item.address, item.name, lines) == ("QUESTIONS.md:3", "Checkout", ["Checkout: why does a refund wait a day?"])
