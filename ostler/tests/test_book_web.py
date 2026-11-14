"""The browser surface of the book runtime, and the todo web book of `fixtures/book_todo` played headless against the stand-in app and its page."""

from __future__ import annotations

import re
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator, cast

import pytest

from book_todo import run_book, module
from ostler.book import Browser, BookError, Journey, Screen, Service, T
from ostler.book.check import spoken
from ostler.book.model import Model
from ostler.book.stack import Stack
from ostler.book.surface import Surface
from ostler.book.screen import Button, Check, Field, Select, Text

PAGE = b"""<!doctype html><html><body>
<h1 id="hello">Hello</h1>
<label for="name">Name</label><input id="name" oninput="document.getElementById('echo').textContent = this.value">
<label for="who">Who</label><select id="who"><option value="">Nobody</option><option value="ana">ana</option></select>
<button type="button" onclick="document.getElementById('echo').textContent = 'pressed'">Go</button>
<input type="checkbox" id="ok"><label for="ok">Agree</label>
<ul><li>first <button onclick="document.getElementById('echo').textContent = 'first'">Pick</button></li>
<li>second <button onclick="document.getElementById('echo').textContent = 'second'">Pick</button></li></ul>
<p id="echo" data-testid="echo"></p>
</body></html>"""


class Form(Screen):
    nick = Field(None, T(en="Name", fr="Nom"))
    who = Select(None, T(en="Who", fr="Qui"), (T(en="Nobody", fr="Personne"), "ana"))
    go = Button(None, T(en="Go", fr="Aller"))
    agree = Check(None, T(en="Agree", fr="D'accord"))
    echo = Text("echo")
    pick = Button(None, T(en="Pick", fr="Choisir"), per_row=True)


@pytest.fixture
def page() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def browser(page: str) -> Iterator[Browser]:
    found = Browser(page, "en", lang_query=None)
    found.start()
    found.open("/")
    yield found
    found.stop()


def test_the_browser_finds_types_and_reads_by_role_and_name(browser: Browser):
    browser.fill(Form.nick, "Ana")
    assert browser.text(Form.echo) == "Ana"
    browser.press(Form.go)
    assert browser.text(Form.echo) == "pressed"
    browser.fill(Form.who, "ana")
    assert browser.value(Form.who) == "ana"
    assert browser.offered(Form.who) == ["", "ana"]
    assert browser.visible(Form.agree)
    assert not browser.disabled(Form.go)


def test_the_browser_finds_a_component_in_the_row_that_holds_a_text(browser: Browser):
    browser.press(Form.pick, row="second")
    assert browser.text(Form.echo) == "second"


def test_a_select_that_does_not_offer_the_value_cannot_be_reached(browser: Browser):
    from ostler.book import CannotReach

    with pytest.raises(CannotReach, match="offers only"):
        browser.fill(Form.who, "zed")


def test_the_browser_names_the_extra_when_playwright_is_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(BookError, match="'qa' extra"):
        Browser("http://127.0.0.1:1").start()


@pytest.fixture
def todo_web() -> Iterator:
    stack = _stack()
    yield stack
    _stop(stack)


def _stack(bug: str | None = None):
    app, web = module("app"), module("web.serve")
    api = app.TodoServer().start()
    page = web.WebServer(api.url, bug=bug)
    threading.Thread(target=page.serve_forever, daemon=True).start()
    return api, page


def _stop(stack) -> None:
    api, page = stack
    api.stop()
    page._server.shutdown()
    page._server.server_close()


def _run(stack, tmp_path: Path, *only: str):
    api, page = stack
    arguments = ["run", "services.web", "--no-stack", "--out", str(tmp_path / "out")]
    for journey in only:
        arguments += ["--journey", journey, "--partial"]
    return run_book(arguments, api.port, web=page.port)


def test_check_finds_nothing_wrong_with_the_web_book(todo_web):
    api, page = todo_web
    done = run_book(["check", "services.web"], api.port, web=page.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "check: 0 findings" in done.stdout


def test_the_journeys_and_the_cells_play_green_headless(todo_web, tmp_path: Path):
    done = _run(todo_web, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "8 pass, 0 known defects, 0 fail" in done.stdout
    assert "cells: 41 played on 23 arrangements, 8 impossible, 0 fail" in done.stdout


@pytest.mark.parametrize("bug, journey", [("wrong-assignee", "EditKeepsWhatWasTyped"), ("drop-last", "ClearTheList")])
def test_a_planted_bug_in_the_page_turns_the_run_red(bug: str, journey: str, tmp_path: Path):
    stack = _stack(bug)
    try:
        done = _run(stack, tmp_path, journey)
    finally:
        _stop(stack)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"FAIL  {journey}" in done.stdout


def test_a_failing_journey_keeps_its_video_and_the_report_names_it_with_an_offset(tmp_path: Path):
    stack = _stack("wrong-assignee")
    try:
        done = _run(stack, tmp_path, "EditKeepsWhatWasTyped")
    finally:
        _stop(stack)
    videos = tmp_path / "out" / "videos"
    assert [v.name for v in videos.iterdir()] == ["EditKeepsWhatWasTyped.webm"]
    assert (videos / "EditKeepsWhatWasTyped.webm").stat().st_size > 0
    assert re.search(r"video: \S+EditKeepsWhatWasTyped\.webm at \d+:\d\d\.\d", done.stdout), done.stdout
    report = (tmp_path / "out" / "web.md").read_text()
    assert re.search(r"## Videos\n\n- EditKeepsWhatWasTyped: EditTodo .*: \d+:\d\d\.\d of \S+\.webm", report), report


def test_a_passing_journey_leaves_no_video_unless_asked(todo_web, tmp_path: Path):
    done = _run(todo_web, tmp_path, "ClearTheList")
    assert done.returncode == 0, done.stdout + done.stderr
    assert list((tmp_path / "out" / "videos").iterdir()) == []
    api, page = todo_web
    kept = run_book(["run", "services.web", "--no-stack", "--journey", "ClearTheList", "--partial", "--keep-videos",
                     "--out", str(tmp_path / "kept")], api.port, web=page.port)
    assert kept.returncode == 0, kept.stdout + kept.stderr
    assert [v.name for v in (tmp_path / "kept" / "videos").iterdir()] == ["ClearTheList.webm"]


def _todo_base():
    from ostler.book.inputs import bases

    service = module("services.web.service").service
    return module("services.web.interactions").AddTodo, bases(service)


def test_a_screen_input_with_a_shape_gets_input_classes():
    from ostler.book.inputs import classes

    add, found = _todo_base()
    base = found[add]
    labels = [c.label for c in classes(base.call, base.before, None)]
    assert labels == ["due_on malformed date"]


def test_a_declared_divergence_on_a_screen_input_names_a_class_the_check_knows():
    import dataclasses

    from ostler.book import Diverges
    from ostler.book.check import input_faults

    add, _ = _todo_base()
    service = module("services.web.service").service
    known = Diverges(add, "due_on malformed date", why="the page keeps any text it is given")
    unknown = Diverges(add, "title missing", why="the page keeps an empty title")
    found = input_faults(dataclasses.replace(service, diverges=(known, unknown)))
    assert [(f.name, f.problem) for f in found if f.name.startswith("diverges")] == [
        ("diverges AddTodo title missing", "no input class of the endpoint has this label")]


def test_a_screen_input_with_a_shape_gets_twins_on_either_side_of_midnight():
    from datetime import timedelta

    from ostler.book.inputs import twin_classes

    add, found = _todo_base()
    base = found[add]
    today = base.before.today
    pairs = [(t.place, t.name, t.dimension, t.left, t.right, t.ignored) for t in twin_classes(base.call, base.before)]
    assert pairs == [("screen", "due_on", "midnight", today.isoformat(), (today + timedelta(days=1)).isoformat(), False)]


def test_the_midnight_twins_count_days_on_the_app_clock_not_the_machine_clock():
    from datetime import date

    from ostler.book.inputs import bases, twin_classes

    service = module("services.web.service").service
    add = module("services.web.interactions").AddTodo
    base = bases(service, date(2030, 1, 5))[add]
    assert [(t.left, t.right) for t in twin_classes(base.call, base.before)] == [("2030-01-05", "2030-01-06")]


def test_a_screen_input_that_ignores_a_dimension_skips_its_twins(monkeypatch: pytest.MonkeyPatch):
    import dataclasses

    from ostler.book import Field as Wire, Str
    from ostler.book.inputs import twin_classes

    add, found = _todo_base()
    form = add.screen
    due = dataclasses.replace(form.due, holds=Wire(Str(format="date"), required=False, ignores=("midnight",), why="the product keeps a day"))
    monkeypatch.setattr(form, "due", due)
    base = found[add]
    assert [t.ignored for t in twin_classes(base.call, base.before)] == [True]


def test_a_screen_input_must_name_the_fixture_field_it_holds():
    from ostler.book import Field as Wire, Str

    with pytest.raises(BookError, match="takes"):
        Field("x", "X", holds=Wire(Str()))


def test_the_twins_of_a_date_pass_when_the_page_keeps_the_day(todo_web, tmp_path: Path):
    done = _run(todo_web, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert re.search(r"twins: [1-9]\d* pairs played, .*, 0 underspecified", done.stdout), done.stdout
    assert "Underspecified" not in done.stdout


def test_a_page_that_sends_the_date_from_a_local_midnight_is_underspecified(tmp_path: Path):
    stack = _stack("utc-midnight")
    try:
        done = _run(stack, tmp_path)
    finally:
        _stop(stack)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "Underspecified (fails the run)" in done.stdout
    assert "- AddTodo screen due_on midnight" in done.stdout


def test_only_takes_the_interactions_of_a_screen_book(todo_web, tmp_path: Path):
    api, page = todo_web
    arguments = ["run", "services.web", "--no-stack", "--only", "RemoveTodo", "--out", str(tmp_path / "out")]
    done = run_book(arguments, api.port, web=page.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "only what calls RemoveTodo" in done.stdout
    assert "0 fail" in done.stdout


def test_a_name_only_cannot_place_is_refused_before_the_stack_starts(tmp_path: Path):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        port = taken.getsockname()[1]
    done = run_book(["run", "services.web", "--only", "ClearTheList", "--out", str(tmp_path / "out")], port, web=port + 1)
    assert done.returncode != 0
    assert "--only names no endpoint or interaction of web: ClearTheList" in done.stderr
    assert "RemoveTodo" in done.stderr
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_a_label_that_gives_two_bare_texts_is_refused():
    with pytest.raises(BookError, match="a label names each language"):
        T("Save", "Enregistrer")


def test_a_label_gives_its_text_in_a_language_it_names():
    label = T(fr="Enregistrer", es="Guardar")
    assert label["es"] == "Guardar"
    with pytest.raises(BookError, match="'en'"):
        label["en"]
    assert T("ana")["es"] == "ana"


def test_a_label_is_the_same_label_whatever_order_its_languages_come_in():
    assert T(en="a", fr="b") == T(fr="b", en="a")
    assert hash(T(en="a", fr="b")) == hash(T(fr="b", en="a"))


class Home(Screen):
    name = T(fr="Accueil", es="Inicio")
    go = Button(None, T(fr="Aller", es="Ir"))


def _service(*screens: type[Screen], languages: tuple[str, ...] = (), journeys: tuple[type[Journey], ...] = ()) -> Service[Model]:
    return Service(name="mini", new_model=Model, surface=lambda environment: cast(Surface, None), journeys=journeys,
                   stack=lambda log_dir: cast(Stack, None), screens=screens, languages=languages)


def test_a_service_with_screens_and_no_languages_is_a_finding():
    found = spoken(_service(Home))
    assert [f.name for f in found] == ["service"]
    assert "declares no languages" in found[0].problem


def test_a_label_that_misses_a_declared_language_or_names_another_is_a_finding():
    class Words(Screen):
        yes = Button(None, T(fr="Oui"))
        both = Button(None, T(fr="Oui", es="Sí", en="Yes"))

    found = [str(f) for f in spoken(_service(Words, languages=("fr", "es")))]
    assert found == [
        "screen Words.yes: the label 'Oui' has no text in es",
        "screen Words.both: the label 'Yes' names en, which the service does not declare; it declares fr, es",
    ]


def test_a_book_of_one_language_writes_bare_strings():
    class Settings(Screen):
        name = "Settings"
        save = Button(None, "Save")

    assert spoken(_service(Settings, languages=("en",))) == []
    assert "'Save'" in Settings.describe("en")
    assert Settings.describe("en").startswith("# Settings")


def test_a_journey_in_a_language_the_service_does_not_declare_is_a_finding():
    class German(Journey):
        lang = "de"

    found = spoken(_service(Home, languages=("fr", "es"), journeys=(German,)))
    assert [str(f) for f in found] == [
        "journey German: plays in 'de', which the service does not declare; it declares fr, es"]


def _locale_of(page: str, lang: str = "", locales: dict[str, str] | None = None) -> tuple[str, str, dict]:
    found = Browser(page, lang, locales=locales)
    found.start()
    options: list[dict] = []
    made = found._browser.new_context

    def spy(**given: object) -> object:
        options.append(given)
        return made(**given)

    found._browser.new_context = spy
    try:
        found._make()
        found.open("/")
        return found.page.evaluate("navigator.language"), found.page.url, options[0]
    finally:
        found.stop()


def test_a_browser_opens_in_the_language_it_was_given(page: str):
    language, url, _ = _locale_of(page, lang="es")
    assert language == "es"
    assert url.endswith("/?lang=es")


def test_a_browser_opens_in_the_locale_its_surface_names_for_the_language(page: str):
    language, _, _ = _locale_of(page, lang="fr", locales={"fr": "fr-CA"})
    assert language == "fr-CA"


def test_a_browser_with_no_language_sets_no_locale_and_no_query(page: str):
    _, url, options = _locale_of(page)
    assert "locale" not in options
    assert "?" not in url


def test_screens_without_lang_prints_the_first_language_of_the_service(tmp_path: Path):
    book = tmp_path / "services" / "mini"
    book.mkdir(parents=True)
    (book / "__init__.py").write_text("")
    (book / "service.py").write_text(
        "from ostler.book import Service, Screen, T\n"
        "from ostler.book.screen import Button\n"
        "class Home(Screen):\n"
        "    name = T(fr='Accueil', es='Inicio')\n"
        "    go = Button(None, T(fr='Aller', es='Ir'))\n"
        "service = Service(name='mini', new_model=lambda today: None, surface=lambda e: None, journeys=(),\n"
        "                  stack=lambda d: None, screens=(Home,), languages=('fr', 'es'))\n")
    done = run_book(["screens", "services.mini"], 0, cwd=tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "# Accueil" in done.stdout and "'Aller'" in done.stdout
    chosen = run_book(["screens", "services.mini", "--lang", "es"], 0, cwd=tmp_path)
    assert "# Inicio" in chosen.stdout
    refused = run_book(["screens", "services.mini", "--lang", "en"], 0, cwd=tmp_path)
    assert refused.returncode != 0
    assert "fr, es" in refused.stdout + refused.stderr
