"""`ostler book search` over a service held in memory: which lines of which items a term reaches."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ostler.book import Answer, Endpoint, Screen, T
from ostler.book.screen import Button, Select
from ostler.book import decisions
from ostler.book.domain import Action, State
from ostler.book.index import services_of
from ostler.book.search import actions_of, cmd_search, items, search

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
    return [hit["title"] for hit in search(service, mod, term, kind)]


def test_a_label_in_the_second_language_of_the_book_finds_its_screen(module: str):
    service = _book(Greeting, languages=("fr", "es"))
    assert _found(service, "Guardar", "screen", module) == ["Greeting"]


def test_the_items_of_a_one_language_book_are_the_lines_of_its_first_language(module: str):
    service = _book(Plain, languages=("en",))
    [screen] = [item for item in items(service, module) if item.kind == "screen"]
    assert screen.lines == tuple(Plain.describe("en").splitlines())


def test_a_source_file_name_finds_the_screen_written_from_it_first(module: str):
    service = _book(Greeting, Plain, languages=("fr",))
    assert _found(service, "greeting.tsx", mod=module)[0] == "Greeting"


def test_a_part_of_a_source_path_finds_the_endpoint_written_from_it(module: str):
    service = _book(endpoints=(Ping, Silent))
    assert _found(service, "api/handlers", mod=module) == ["Ping"]


def test_an_element_with_no_source_has_no_source_line(module: str):
    service = _book(endpoints=(Silent,))
    [endpoint] = [item for item in items(service, module) if item.kind == "endpoint"]
    assert not [line for line in endpoint.lines if line.startswith("source:")]


def test_two_words_that_sit_apart_on_one_screen_find_it_first(module: str):
    service = _book(Greeting, Plain, languages=("fr", "es"))
    assert _found(service, "enregistrer aller", mod=module)[0] == "Greeting"


def test_the_screen_holding_every_word_ranks_above_one_holding_a_few(module: str):
    service = _book(Editor, Plain, languages=("en",))
    assert _found(service, "save changes", "screen", module)[0] == "Editor"


def test_words_no_item_holds_find_nothing_and_exit_one(module: str, capsys):
    service = _book(Greeting, Plain, languages=("fr",))
    args = SimpleNamespace(service=module, term="zebra quartz", kind=None)
    assert cmd_search(service, args) == 1
    assert capsys.readouterr().out == "nothing in mini says 'zebra quartz'\n"


def test_kind_narrows_the_hits(module: str):
    service = _book(Plain, endpoints=(Store,), languages=("en",))
    assert {"Plain", "Store"} <= set(_found(service, "save settings", mod=module))
    assert _found(service, "save settings", "endpoint", module) == ["Store"]
    assert _found(service, "save settings", "screen", module) == ["Plain"]


def test_a_hit_marks_the_words_it_matched(module: str, capsys):
    service = _book(Greeting, languages=("fr", "es"))
    args = SimpleNamespace(service=module, term="enregistrer aller", kind="screen")
    assert cmd_search(service, args) == 0
    out = capsys.readouterr().out
    assert "books/screen" in out and "[Enregistrer]" in out and "[Aller]" in out


def _decided(module: str) -> None:
    folder = decisions.directory(module)
    with open(os.path.join(folder, "refund.md"), "w") as f:
        f.write("story: SHOP-42\ndate: 2026-11-14\nelements: Checkout, Cart\nsources: app.py::refund\n\nA refund keeps the basket.\n")


def _decision(module: str, term: str) -> dict:
    _decided(module)
    [hit] = search(_book(languages=("en",)), module, term, "decision")
    assert hit["node"] == f"{module}/decisions/refund.md"
    return hit


def test_a_story_id_finds_its_decision(module: str):
    assert "[SHOP]-[42]" in _decision(module, "SHOP-42")["snippet"]


def test_a_class_name_finds_the_decision_that_explains_it(module: str):
    assert "[Cart]" in _decision(module, "Cart")["snippet"]


def test_a_cited_source_finds_its_decision(module: str):
    assert "[app].[py]::[refund]" in _decision(module, "app.py::refund")["snippet"]


def test_a_word_of_an_open_question_finds_it(module: str):
    questions = os.path.join(os.path.dirname(decisions.directory(module)), "QUESTIONS.md")
    with open(questions, "w") as f:
        f.write("# Open\n\n- Checkout: why does a refund wait a day?\n")
    [hit] = search(_book(languages=("en",)), module, "refund wait", "question")
    assert (hit["node"], hit["title"]) == (f"{module}/QUESTIONS.md:3", "Checkout")


@pytest.mark.parametrize("options", ["ana", T(en="Ana", fr="Anne")])
def test_a_select_handed_one_text_for_its_options_is_refused(options: Any):
    with pytest.raises(TypeError, match="options takes a list of texts, not one text"):
        Select(None, "Who", options=options)


def test_a_selects_third_word_says_what_it_does_as_for_every_other_component():
    picked = Select(None, "Who", "picks the owner")
    assert (picked.does, picked.options) == ("picks the owner", ())


def test_a_select_handed_its_options_by_position_is_refused():
    with pytest.raises(TypeError, match="options are given by name"):
        Select(None, "Who", cast(Any, ("ana", "bo")))


def test_the_books_under_a_root_are_its_service_files_one_per_surface(tmp_path: Path):
    for file in ("shop/service.py", "desk/http/service.py", "desk/web/service.py", "desk/model/state.py", "ops/stack.yml"):
        (tmp_path / "services" / file).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "services" / file).write_text("")
    assert services_of(str(tmp_path)) == ["services.desk.http", "services.desk.web", "services.shop"]


def test_the_books_under_a_namespaced_root_are_found_one_repository_folder_deep(tmp_path: Path):
    for file in ("acme/api/service.py", "acme/groom/http/service.py", "acme/groom/model/state.py", "globex/api/service.py"):
        (tmp_path / "services" / file).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "services" / file).write_text("")
    assert services_of(str(tmp_path)) == ["services.acme.api", "services.acme.groom.http", "services.globex.api"]
    assert services_of(str(tmp_path), "services.acme") == ["services.acme.api", "services.acme.groom.http"]


def test_actions_of_excludes_sibling_packages_sharing_a_module_name_prefix(
    module: str,
    monkeypatch: pytest.MonkeyPatch,
):
    sibling_mod_name = f"{module}-retention.model.actions"
    sibling_mod = SimpleNamespace()
    monkeypatch.setitem(os.sys.modules, sibling_mod_name, sibling_mod)
    sibling_action = type("SweepRetention", (Action,), {"__module__": sibling_mod_name})
    setattr(sibling_mod, "SweepRetention", sibling_action)
    assert sibling_action not in actions_of(_book(languages=("en",)), module)

