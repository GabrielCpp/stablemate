"""The browser surface of the book runtime, and the todo web book of `fixtures/book_todo` played headless against the stand-in app and its page."""

from __future__ import annotations

import re
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator, cast

import pytest

from book_fakes import Quiet
from book_todo import run_book, module
from ostler.book import Browser, BookError, Field as Wire, Int, Journey, Screen, Service, T
from ostler.book.check import spoken
from ostler.book.model import Model
from ostler.book.outcome import Refusal, Refusals
from ostler.book.stack import Stack
from ostler.book.surface import Surface
from ostler.book.browser import request
from ostler.book.screen import Button, Check, Field, Lists, Select, Text

PAGE = b"""<!doctype html><html><body>
<h1 id="hello">Hello</h1>
<label for="name">Name</label><input id="name" oninput="document.getElementById('echo').textContent = this.value">
<label for="short">Short</label><input id="short" data-testid="short" maxlength="5">
<label for="qty">Quantity</label><input id="qty" data-testid="qty" type="number">
<label for="who">Who</label><select id="who"><option value="">Nobody</option><option value="ana">ana</option></select>
<button type="button" onclick="document.getElementById('echo').textContent = 'pressed'">Go</button>
<input type="checkbox" id="ok"><label for="ok">Agree</label>
<ul><li>first <button onclick="document.getElementById('echo').textContent = 'first'">Pick</button></li>
<li>second <button onclick="document.getElementById('echo').textContent = 'second'">Pick</button></li></ul>
<p id="echo" data-testid="echo"></p>
</body></html>"""


class Form(Screen):
    nick = Field(None, T(en="Name", fr="Nom"))
    short = Field("short", T(en="Short", fr="Court"))
    qty = Field("qty", T(en="Quantity", fr="Quantité"), takes="qty", holds=Wire(Int()))
    who = Select(None, T(en="Who", fr="Qui"), options=(T(en="Nobody", fr="Personne"), "ana"))
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


def test_an_input_typed_one_character_past_its_limit_cannot_be_reached(browser: Browser):
    from ostler.book import CannotReach

    with pytest.raises(CannotReach, match="keeps only its first 5 characters of 6 typed"):
        browser.fill(Form.short, "x" * 6)


def test_an_input_typed_up_to_its_limit_is_typed_whole(browser: Browser):
    browser.fill(Form.short, "x" * 5)
    assert browser.value(Form.short) == "x" * 5


def test_an_input_with_no_limit_is_typed_whole(browser: Browser):
    browser.fill(Form.nick, "x" * 300)
    assert browser.value(Form.nick) == "x" * 300


def _too_long_at_the_limit(browser: Browser, by_a_rule: bool = False, refusals: Refusals | None = None):
    from ostler.book import Answer, Done, Endpoint, Object, Str
    from ostler.book import Field as Body
    from ostler.book.inputs import InputClass, judge
    from ostler.book.domain import Action
    from ostler.book.model import Refused, Rule

    class Open(Action):
        pass

    class Send(Endpoint):
        carries = Open
        method = "POST"
        path = "/send"
        body = Object("Send", short=Body(Str(max_len=5)))
        answers = (Answer(200, None, "sent"),)

    class Typing(Quiet):
        def perform(self, step):
            browser.fill(Form.short, step.body_value["short"])
            return Done()

    class Empty(Model):
        def apply(self, request: Any):
            if by_a_rule and len(request.body_value["short"]) > 5:
                raise Refused(Rule("too long", lambda a, s, by: True))
            return None

        def rows(self):
            return ()

        def copy(self):
            return Empty(self.today)

    from datetime import date
    from ostler.book.inputs import vary

    chosen = InputClass("body", "short", "too long", "x" * 6, False, "malformed")
    call = vary(Send({"short": "ab"}), chosen)
    service = Service[Empty](name="x", new_model=Empty, surface=lambda environment: Typing(), journeys=(),
                             stack=lambda directory: Stack((), directory), refusals=refusals or Refusals())
    return judge(service, call, chosen, Empty(date(2026, 11, 4)), Typing())


def test_a_too_long_class_at_an_input_that_stops_at_its_limit_passes_as_unreachable_by_a_default_key(browser: Browser):
    sent = _too_long_at_the_limit(browser, refusals=Refusals(malformed=Refusal("too long", 400)))
    assert sent.ok, sent.note
    assert "keeps only its first 5 characters of 6 typed" in sent.outcome


def test_a_too_long_class_at_an_input_that_stops_at_its_limit_passes_as_unreachable_by_a_rule(browser: Browser):
    sent = _too_long_at_the_limit(browser, by_a_rule=True)
    assert sent.ok, sent.note
    assert "keeps only its first 5 characters of 6 typed" in sent.outcome


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


def test_a_stack_walk_under_a_caller_with_no_file_does_not_search_the_modules(monkeypatch: pytest.MonkeyPatch):
    import inspect
    import linecache

    from ostler.book.browser import known_callers

    nowhere = "<a caller with no file>"
    assert nowhere not in linecache.cache
    searched: list[str] = []
    real = inspect.getmodule

    def getmodule(thing: Any, _filename: str | None = None) -> Any:
        searched.append(str(_filename))
        return real(thing, _filename)

    monkeypatch.setattr(inspect, "getmodule", getmodule)
    scope: dict[str, Any] = {"known_callers": known_callers, "inspect": inspect}
    try:
        exec(compile("known_callers()\nfound = [f.filename for f in inspect.stack(0)]", nowhere, "exec"), scope)
    finally:
        linecache.cache.pop(nowhere, None)
    assert nowhere in scope["found"]
    assert nowhere not in searched


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


@dataclass(frozen=True)
class FullRun:
    """One whole run of the web book against the correct page, and the folder it wrote."""

    done: subprocess.CompletedProcess[str]
    out: Path


@pytest.fixture(scope="module")
def full_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[FullRun]:
    """The whole web book played once, read by every test that judges a complete run."""
    stack = _stack()
    try:
        tmp_path = tmp_path_factory.mktemp("full-run")
        yield FullRun(_run(stack, tmp_path), tmp_path / "out")
    finally:
        _stop(stack)


def full_run_group[F: Callable[..., object]](test: F) -> F:
    """A test that reads the shared whole run: on the one worker that plays it, handed out first."""
    return pytest.mark.whole_run(pytest.mark.xdist_group("web-book-full-run")(test))


def test_check_finds_nothing_wrong_with_the_web_book(todo_web):
    api, page = todo_web
    done = run_book(["check", "services.web"], api.port, web=page.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "check: 0 findings" in done.stdout


@full_run_group
def test_the_journeys_and_the_cells_play_green_headless(full_run: FullRun):
    done = full_run.done
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


def test_a_page_that_shows_the_users_in_the_order_received_fails_the_step_that_picks_in_the_list(tmp_path: Path):
    stack = _stack("unsorted-users")
    try:
        done = _run(stack, tmp_path, "AWeekOfChores")
    finally:
        _stop(stack)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the list AddForm.assignee shows ['Nobody', 'bo', 'ana'], the book derives ['Nobody', 'ana', 'bo']" in done.stdout


def test_a_page_that_leaves_a_user_out_fails_the_step_that_picks_in_the_filter_and_names_the_user(tmp_path: Path):
    stack = _stack("missing-user")
    try:
        done = _run(stack, tmp_path, "AWeekOfChores")
    finally:
        _stop(stack)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the list ListPage.assignee misses ['bo'], which belong in it" in done.stdout


def test_a_page_that_leaves_no_user_out_passes_the_step_that_picks_in_the_filter(todo_web, tmp_path: Path):
    done = _run(todo_web, tmp_path, "AWeekOfChores")
    assert done.returncode == 0, done.stdout + done.stderr


@full_run_group
def test_the_report_of_a_run_names_the_lists_a_journey_picked_in(full_run: FullRun):
    done = full_run.done
    assert done.returncode == 0, done.stdout + done.stderr
    listed = "Lists\nstated and read:\n- ListPage.assignee\n- ListPage.details\n- AddForm.assignee\n- EditForm.assignee\nstated and never read:\n- none\nnamed only:\n- none\n"
    assert listed in done.stdout
    assert "## Lists\n\nstated and read:\n- ListPage.assignee" in (full_run.out / "web.md").read_text()


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
    assert labels == ["title blank", "title too long", "title missing", "description too long", "due_on malformed date"]


def _classes_of(shape, place: str, required: bool = True) -> list[str]:
    from ostler.book import Field as Wire
    from ostler.book.inputs import field_classes

    add, found = _todo_base()
    return [c.label for c in field_classes(place, "x", Wire(shape, required=required), found[add].before, None)]


def test_a_required_text_on_a_screen_is_tried_blank():
    from ostler.book import Str

    assert "x blank" in _classes_of(Str(max_len=5), "screen")


def test_an_optional_text_on_a_screen_is_not_tried_blank():
    from ostler.book import Str

    assert "x blank" not in _classes_of(Str(max_len=5), "screen", required=False)


def test_a_number_on_a_screen_is_tried_with_text():
    from ostler.book import Int, Num

    assert "x malformed number" in _classes_of(Int(), "screen")
    assert "x malformed number" in _classes_of(Num(), "screen")


def test_a_number_that_is_not_on_a_screen_is_not_tried_with_text():
    from ostler.book import Int, Num

    for place in ("path", "query", "body", "headers"):
        assert "x malformed number" not in _classes_of(Int(), place)
        assert "x malformed number" not in _classes_of(Num(), place)


def test_a_browser_that_rejects_text_in_a_number_makes_the_class_unreachable(browser: Browser):
    from ostler.book import CannotReach

    with pytest.raises(CannotReach, match="does not take 'not a number'"):
        browser.fill(Form.qty, "not a number")


def test_the_fixture_web_book_states_a_shape_for_every_field_a_person_fills():
    service = module("services.web.service").service
    bare = [f"{screen.__name__}.{name}" for screen in service.screens for name, c in screen.attributes()
            if c.kind in ("field", "textarea", "date") and c.holds is None]
    assert bare == []


def test_an_interaction_gets_only_the_typed_fields_its_fixture_has():
    from ostler.book.inputs import has_inputs, input_fields
    from ostler.book.screen import Interaction

    interactions = module("services.web.interactions")
    actions = module("services.web.model.actions")
    hooks = module("services.web.fixtures.hooks")
    peek = type("PeekAtTheForm", (Interaction,), {"screen": interactions.AddTodo.screen, "carries": actions.MoveClock,
                                                  "source": ("web/app.js",), "does": "looks at the add form as a day passes"})
    assert [c.takes for c in interactions.AddTodo.typed()] == ["title", "description", "due_on"]
    assert peek.typed() == []
    assert not has_inputs(peek)
    assert list(input_fields(peek(hooks.Clock(today="2026-01-01")))) == []


def _faults_of(**components):
    import dataclasses

    from ostler.book.check import shape_faults

    service = module("services.web.service").service
    screen = type("Bare", (Screen,), components)
    return [(f.name, f.problem, f.blocks) for f in shape_faults(dataclasses.replace(service, screens=(screen,)))]


def test_a_component_named_name_is_a_finding_and_does_not_crash_the_language_check():
    from ostler.book.check import name_faults

    Team = type("Team", (Screen,), {"name": Field(None, "Name")})

    found = [str(f) for f in name_faults(_service(Team))]
    assert found == ["screen Team.name: `name` is the screen's own name, and here it holds a component; give the component another attribute name"]
    assert spoken(_service(Team, languages=("en",))) == []


def test_the_check_names_a_field_that_states_no_shape():
    problem = "a person fills it and it states no shape, so no input is tried on it: give it takes= and holds="
    from ostler.book.screen import DateField, TextArea

    found = _faults_of(name=Field(None, "Name"), notes=TextArea(None, "Notes"), day=DateField(None, "Day"))
    assert found == [("screen Bare.name", problem, True), ("screen Bare.notes", problem, True), ("screen Bare.day", problem, True)]


def test_the_check_names_a_select_that_states_no_options_no_list_and_no_shape():
    found = _faults_of(who=Select(None, "Who"))
    assert found == [("screen Bare.who", "a person picks in it and it states neither its options, what its list holds, nor a shape", True)]


def test_a_select_that_states_its_options_gets_no_finding():
    from ostler.book import Str

    assert _faults_of(who=Select(None, "Who", options=("ana",)), size=Select(None, "Size", takes="size", holds=Wire(Str())),
                      nick=Field(None, "Nick", takes="nick", holds=Wire(Str()))) == []


def test_a_select_that_states_what_its_list_holds_gets_no_finding():
    def nobody(model, by):
        """no one"""
        return []

    assert _faults_of(who=Select(None, "Who", lists=Lists(never=nobody))) == []


def _unfilled_of(filled_on_own_screen: bool, **components):
    import dataclasses

    from ostler.book.check import fill_faults
    from ostler.book.screen import Interaction

    service = module("services.web.service").service
    actions = module("services.web.model.actions")
    screen = type("Bare", (Screen,), components)
    fills = type("FillsBare", (Interaction,), {"screen": screen if filled_on_own_screen else module("services.web.screens").ListPage,
                                               "carries": actions.Add, "source": ("web/app.js",), "does": "fills a form"})
    return [(f.name, f.problem, f.blocks) for f in fill_faults(dataclasses.replace(service, screens=(screen,), interactions=(fills,)))]


def test_the_check_names_a_field_that_states_a_shape_and_that_no_interaction_fills():
    from ostler.book import Str

    found = _unfilled_of(False, title=Field(None, "Title", takes="title", holds=Wire(Str())))
    assert found == [("screen Bare.title", "it states a shape and no interaction of the book fills it, so no input is tried on it: "
                      "give an interaction of this screen a fixture that has title", False)]


def test_a_stated_field_that_nothing_fills_fails_the_check_and_does_not_stop_a_run():
    from ostler.book import Str

    (_, _, blocks), = _unfilled_of(False, title=Field(None, "Title", takes="title", holds=Wire(Str())))
    assert blocks is False


def test_a_field_that_an_interaction_of_its_screen_fills_gets_no_such_finding():
    from ostler.book import Str

    assert _unfilled_of(True, title=Field(None, "Title", takes="title", holds=Wire(Str()))) == []


def test_a_field_that_only_an_interaction_of_another_screen_has_in_its_fixture_is_still_named():
    from ostler.book import Str

    found = _unfilled_of(False, title=Field(None, "Title", takes="title", holds=Wire(Str())), who=Select(None, "Who", options=("ana",)))
    assert [name for name, _, _ in found] == ["screen Bare.title"]


def test_the_fixture_web_book_has_no_stated_field_that_nothing_fills():
    from ostler.book.check import fill_faults

    assert fill_faults(module("services.web.service").service) == []


def test_a_declared_divergence_on_a_screen_input_names_a_class_the_check_knows():
    import dataclasses

    from ostler.book import Diverges
    from ostler.book.check import input_faults

    add, _ = _todo_base()
    service = module("services.web.service").service
    known = Diverges(add, "due_on malformed date", why="the page keeps any text it is given")
    unknown = Diverges(add, "title null", why="the page keeps an empty title")
    found = input_faults(dataclasses.replace(service, diverges=(known, unknown)))
    assert [(f.name, f.problem) for f in found if f.name.startswith("diverges")] == [
        ("diverges AddTodo title null", "no input class of the endpoint has this label")]


def test_a_screen_input_with_a_shape_gets_twins_on_either_side_of_midnight():
    from datetime import timedelta

    from ostler.book.inputs import twin_classes

    add, found = _todo_base()
    base = found[add]
    today = base.before.today
    pairs = [(t.place, t.name, t.dimension, t.left, t.right, t.ignored) for t in twin_classes(base.call, base.before) if t.name == "due_on"]
    assert pairs == [("screen", "due_on", "midnight", today.isoformat(), (today + timedelta(days=1)).isoformat(), False)]


def test_the_midnight_twins_count_days_on_the_app_clock_not_the_machine_clock():
    from datetime import date

    from ostler.book.inputs import bases, twin_classes

    service = module("services.web.service").service
    add = module("services.web.interactions").AddTodo
    base = bases(service, date(2030, 1, 5))[add]
    assert [(t.left, t.right) for t in twin_classes(base.call, base.before) if t.name == "due_on"] == [("2030-01-05", "2030-01-06")]


def test_a_screen_input_that_ignores_a_dimension_skips_its_twins(monkeypatch: pytest.MonkeyPatch):
    import dataclasses

    from ostler.book import Field as Wire, Str
    from ostler.book.inputs import twin_classes

    add, found = _todo_base()
    form = add.screen
    due = dataclasses.replace(form.due, holds=Wire(Str(format="date"), required=False, ignores=("midnight",), why="the product keeps a day"))
    monkeypatch.setattr(form, "due", due)
    base = found[add]
    assert [t.ignored for t in twin_classes(base.call, base.before) if t.name == "due_on"] == [True]


def _twin_dimensions(name: str, as_select: tuple[str, ...]) -> list[str]:
    import dataclasses

    from ostler.book.inputs import twin_classes

    add, found = _todo_base()
    form = add.screen
    originals = {field: getattr(form, field) for field in as_select}
    try:
        for field, component in originals.items():
            setattr(form, field, dataclasses.replace(component, kind="select"))
        base = found[add]
        return [t.dimension for t in twin_classes(base.call, base.before) if t.name == name]
    finally:
        for field, component in originals.items():
            setattr(form, field, component)


def test_a_select_that_states_a_shape_gets_no_case_or_space_twin():
    assert _twin_dimensions("title", ()) == ["surrounding spaces", "case"]
    assert _twin_dimensions("title", ("title",)) == []


def test_a_text_field_of_the_same_shape_on_the_same_screen_still_gets_the_case_and_space_twins():
    assert _twin_dimensions("description", ("title",)) == ["surrounding spaces", "case"]


def test_a_date_typed_into_a_screen_keeps_its_midnight_twin_when_the_screen_has_a_select():
    assert _twin_dimensions("due_on", ("title",)) == ["midnight"]


@full_run_group
def test_the_run_of_the_web_book_plays_the_same_pairs_as_before(full_run: FullRun):
    done = full_run.done
    assert done.returncode == 0, done.stdout + done.stderr
    assert "twins: 9 pairs played, 1 skipped because the model distinguished them, 0 underspecified" in done.stdout.splitlines()


def test_a_screen_input_must_name_the_fixture_field_it_holds():
    from ostler.book import Field as Wire, Str

    with pytest.raises(BookError, match="takes"):
        Field("x", "X", holds=Wire(Str()))


@full_run_group
def test_the_twins_of_a_date_pass_when_the_page_keeps_the_day(full_run: FullRun):
    done = full_run.done
    assert done.returncode == 0, done.stdout + done.stderr
    assert re.search(r"twins: [1-9]\d* pairs played, .*, 0 underspecified", done.stdout), done.stdout
    assert "Underspecified" not in done.stdout


@full_run_group
def test_the_run_of_the_web_book_plays_the_input_classes_its_forms_state(full_run: FullRun):
    done = full_run.done
    assert done.returncode == 0, done.stdout + done.stderr
    played = re.search(r"inputs: (\d+) played, \d+ diverge as declared, 0 fail", done.stdout)
    assert played and int(played.group(1)) > 2, done.stdout


@full_run_group
def test_the_run_of_the_web_book_prints_how_many_stated_fields_it_tried_and_tried_every_one(full_run: FullRun):
    done = full_run.done
    assert done.returncode == 0, done.stdout + done.stderr
    said = re.search(r"^fields: (\d+) state a shape, (\d+) tried$", done.stdout, re.MULTILINE)
    assert said and int(said.group(1)) > 0 and said.group(1) == said.group(2), done.stdout
    assert done.stdout.index("twins:") < done.stdout.index("fields:")


@pytest.mark.whole_run
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


def by_name(users):
    """the users received, by name"""
    return sorted(u["name"] for u in users)


def test_a_select_given_a_feed_without_a_derivation_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="both given and derived.*no derived"):
        Lists(given=request("GET", "/users"))
    with pytest.raises(BookError, match="both given and derived.*no given"):
        Lists(derived=by_name)


def test_a_derivation_with_no_docstring_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="has no docstring"):
        Lists(given=request("GET", "/users"), derived=lambda users: [u["name"] for u in users])


def test_a_list_that_states_nothing_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="states nothing"):
        Lists(head=("Anyone",))


@pytest.mark.parametrize("claim", ["always", "never"])
def test_a_claim_about_who_belongs_with_no_docstring_is_refused_where_it_is_declared(claim: str):
    with pytest.raises(BookError, match=f"the {claim} function .* has no docstring"):
        Lists(**cast(dict, {claim: lambda model, by: []}))


def test_a_select_given_both_fixed_options_and_a_derived_list_is_refused():
    derived = Lists(given=request("GET", "/users"), derived=by_name)
    with pytest.raises(BookError, match="not both"):
        Select("who", "Who", options=("ana",), lists=derived)


def test_the_description_of_a_screen_says_what_a_derived_list_holds():
    class People(Screen):
        who = Select("who", T(en="Who", fr="Qui"), "filters by owner",
                     lists=Lists(head=(T(en="Anyone", fr="Tous"),), given=request("GET", "/users"), derived=by_name))

    assert "lists: 'Anyone', the users received, by name" in People.describe("en")
    assert "lists: 'Tous', the users received, by name" in People.describe("fr")


class People(Screen):
    who = Select("who", "Who", lists=Lists(head=("Anyone",), given=request("GET", "/users"), derived=by_name))


def owners(model, by):
    """everyone a todo the list holds is assigned to"""
    return sorted({t.assignee for t in model.todos if t.assignee})


def not_me(model, by):
    """the person looking"""
    return [by.handle]


class Members(Screen):
    who = Select("who", "Who", lists=Lists(head=("Anyone",), always=owners, never=not_me))


def test_the_description_of_a_screen_says_who_belongs_in_a_list_and_who_never_does():
    class Owners(Screen):
        who = Select("who", T(en="Who", fr="Qui"), "filters by owner",
                     lists=Lists(head=(T(en="Anyone", fr="Tous"),), given=request("GET", "/users"), derived=by_name,
                                 always=owners, never=not_me))

    assert ("lists: 'Anyone', the users received, by name; always everyone a todo the list holds is assigned to; "
            "never the person looking") in Owners.describe("en")
    assert "lists: 'Tous', the users received, by name; always everyone" in Owners.describe("fr")


@contextmanager
def _people_page(sort: bool = True, screens: tuple[type[Screen], ...] = (People,)) -> Iterator[Browser]:
    ordered = "us.sort((a, b) => a.name.localeCompare(b.name));" if sort else ""
    body = (
        '<!doctype html><html><body><select id="who" data-testid="who"><option value="">Anyone</option></select>'
        "<script>fetch('/users').then(r => r.json()).then(us => {" + ordered +
        "for (const u of us) document.getElementById('who').append(new Option(u.name, u.name));"
        "});</script></body></html>").encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            users = self.path == "/users"
            payload = b'[{"name": "bo"}, {"name": "ana"}]' if users else body
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if users else "text/html")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    found = Browser(f"http://127.0.0.1:{server.server_address[1]}", "en", lang_query=None)
    found.feeding(screens)
    found.start()
    try:
        yield found
    finally:
        found.stop()
        server.shutdown()
        server.server_close()


def _shows_the_users(browser: Browser) -> None:
    browser.page.wait_for_function("document.getElementById('who').options.length === 3")


def test_a_pick_in_a_derived_list_passes_when_the_page_shows_what_the_book_derives():
    with _people_page() as browser:
        browser.open("/")
        _shows_the_users(browser)
        browser.fill(People.who, "ana")
        assert browser.list_faults() == []
        assert browser.lists_read() == {"People.who"}


def test_a_pick_in_a_derived_list_fails_when_the_page_shows_the_users_in_the_order_received():
    with _people_page(sort=False) as browser:
        browser.open("/")
        _shows_the_users(browser)
        browser.fill(People.who, "ana")
        assert browser.list_faults() == [
            "the list People.who shows ['Anyone', 'bo', 'ana'], the book derives ['Anyone', 'ana', 'bo']"]


def _expects(always: list[str], never: list[str]) -> dict:
    return {"Members.who": (always, never)}


def test_a_pick_passes_when_everyone_who_belongs_is_offered_among_entries_the_book_never_named():
    with _people_page(screens=(Members,)) as browser:
        browser.open("/")
        _shows_the_users(browser)
        browser.expecting(_expects(["ana"], ["zed"]))
        browser.fill(Members.who, "ana")
        assert browser.list_faults() == []
        assert browser.lists_read() == {"Members.who"}


def test_a_pick_fails_when_someone_who_belongs_is_missing_and_the_note_names_the_list_and_who():
    with _people_page(screens=(Members,)) as browser:
        browser.open("/")
        _shows_the_users(browser)
        browser.expecting(_expects(["ana", "cy"], []))
        browser.fill(Members.who, "ana")
        assert browser.list_faults() == ["the list Members.who misses ['cy'], which belong in it"]


def test_a_pick_fails_when_someone_who_must_never_be_in_the_list_is_offered_and_the_note_names_who():
    with _people_page(screens=(Members,)) as browser:
        browser.open("/")
        _shows_the_users(browser)
        browser.expecting(_expects([], ["bo", "zed"]))
        browser.fill(Members.who, "ana")
        assert browser.list_faults() == ["the list Members.who shows ['bo'], which must never be in it"]


def test_a_list_picked_in_outside_a_step_is_judged_on_its_derived_claim_alone():
    class Both(Screen):
        who = Select("who", "Who", lists=Lists(head=("Anyone",), given=request("GET", "/users"), derived=by_name,
                                                always=owners, never=not_me))

    with _people_page(sort=False, screens=(Both,)) as browser:
        browser.open("/")
        _shows_the_users(browser)
        browser.fill(Both.who, "ana")
        assert browser.list_faults() == [
            "the list Both.who shows ['Anyone', 'bo', 'ana'], the book derives ['Anyone', 'ana', 'bo']"]


class Look(Screen):
    who = Select("who", "Who", lists=Lists(always=owners, never=not_me))


class Looks:
    screen = Look

    def __init__(self, by: object) -> None:
        self.by = by


class Keeper:
    def __init__(self) -> None:
        self.todos = [type("Todo", (), {"assignee": "ana"})()]
        self.today = None

    def perform(self, request: object):
        from ostler.book.outcome import Done

        self.todos = []
        return Done(())

    def rows(self):
        return ()


class Watcher:
    name = "stub"

    def __init__(self) -> None:
        self.handed: list[dict] = []

    def expecting(self, expectations: dict) -> None:
        self.handed.append(dict(expectations))

    def perform(self, request: object):
        from ostler.book.outcome import Done

        return Done(())

    def rows(self):
        return ()


def test_who_belongs_is_taken_from_the_model_before_the_step_changes_it():
    from ostler.book.cast import Actor
    from ostler.book.runner import perform

    model, surface = Keeper(), Watcher()
    perform("look", Looks(Actor("bo")), cast(Model, model), cast(Surface, surface))
    assert surface.handed == [{"Look.who": (["ana"], ["bo"])}, {}]
    assert model.todos == []


def test_a_step_of_no_screen_hands_the_surface_nothing():
    from ostler.book.runner import perform

    class Elsewhere:
        screen = None
        by = None

    surface = Watcher()
    perform("elsewhere", Elsewhere(), cast(Model, Keeper()), cast(Surface, surface))
    assert surface.handed == []


def test_a_claim_that_raises_fails_the_step_before_the_model_moves_and_the_note_names_the_list_and_the_error():
    from ostler.book.runner import attempt

    model = Keeper()
    done = attempt(Looks(None), cast(Model, model), cast(Surface, Watcher()))
    assert not done.ok
    assert "the list Look.who" in done.note and "AttributeError" in done.note
    assert len(model.todos) == 1


def test_a_pick_made_before_the_page_received_the_answer_is_a_fault_that_says_so():
    with _people_page() as browser:
        with browser.holding(request("GET", "/users")):
            browser.open("/")
            browser.fill(People.who, "")
            assert browser.list_faults() == [
                "the page received no answer to GET /users before the pick in People.who"]


def test_the_account_of_lists_names_a_stated_list_as_read_and_a_select_with_nothing_stated_as_named_only():
    from ostler.book.listing import account

    class Pickers(Screen):
        fixed = Select("fixed", "Fixed", options=("a",))
        who = People.who
        free = Select("free", "Free")
        idle = Select("idle", "Idle", lists=Lists(given=request("GET", "/users"), derived=by_name))

    assert account((Pickers,), frozenset({"Pickers.who"})) == [
        "Lists", "stated and read:", "- Pickers.who", "stated and never read:", "- Pickers.idle", "named only:", "- Pickers.free"]


def test_a_book_with_no_select_gets_no_account_of_lists():
    from ostler.book.listing import account

    assert account((Home,), frozenset()) == []


class Chooser(Screen):
    who = Select("who", "Who")


class Popup(Screen):
    who = Select("who", "Who", lists=Lists(head=("Anyone",), given=request("GET", "/users"), derived=by_name))


@contextmanager
def _popup_page(sort: bool = True, ids: bool = False) -> Iterator[Browser]:
    ordered = "us.sort((a, b) => a.name.localeCompare(b.name));" if sort else ""
    shown = "'u-' + u.name" if ids else "null"
    body = (
        '<!doctype html><html><body>'
        '<button id="who" data-testid="who" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-controls="lb">Anyone</button>'
        '<ul id="lb" role="listbox" hidden></ul><p id="picked"></p>'
        "<script>"
        "const box = document.getElementById('who'), lb = document.getElementById('lb');"
        "const shut = () => { lb.hidden = true; box.setAttribute('aria-expanded', 'false'); };"
        "function add(value, text) {"
        "  const li = document.createElement('li'); li.setAttribute('role', 'option'); li.textContent = text;"
        "  if (value !== null) li.setAttribute('data-value', value);"
        "  li.addEventListener('click', () => { document.getElementById('picked').textContent = value === null ? text : value;"
        "    box.textContent = text; shut(); });"
        "  lb.append(li);"
        "}"
        "add('', ' Anyone ');"
        "fetch('/users').then(r => r.json()).then(us => {" + ordered +
        "for (const u of us) add(" + shown + ", u.name); lb.dataset.ready = 'yes'; });"
        "box.addEventListener('click', () => { lb.hidden = false; box.setAttribute('aria-expanded', 'true'); });"
        "document.addEventListener('keydown', (e) => { if (e.key === 'Escape') shut(); });"
        "</script></body></html>").encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            users = self.path == "/users"
            payload = b'[{"name": "bo"}, {"name": "ana"}]' if users else body
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if users else "text/html")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    found = Browser(f"http://127.0.0.1:{server.server_address[1]}", "en", lang_query=None)
    found.feeding((Popup,))
    found.start()
    try:
        found.open("/")
        found.page.wait_for_selector("#lb[data-ready=yes]", state="attached")
        yield found
    finally:
        found.stop()
        server.shutdown()
        server.server_close()


def test_a_pick_in_a_popup_dropdown_selects_the_entry_with_that_value():
    with _popup_page(ids=True) as browser:
        browser.fill(Chooser.who, "u-ana")
        assert browser.page.inner_text("#picked") == "u-ana"
        assert browser.page.get_by_role("listbox").count() == 0


def test_a_pick_by_label_selects_the_entry_when_no_entry_has_that_value():
    with _popup_page(ids=True) as browser:
        browser.fill(Chooser.who, "bo")
        assert browser.page.inner_text("#picked") == "u-bo"


def test_a_popup_that_does_not_offer_the_value_is_closed_again_and_cannot_be_reached():
    from ostler.book import CannotReach

    with _popup_page() as browser:
        with pytest.raises(CannotReach, match=r"offers only \['', 'ana', 'bo'\]"):
            browser.fill(Chooser.who, "zed")
        assert browser.page.get_attribute("#who", "aria-expanded") == "false"
        assert browser.page.inner_text("#picked") == ""


def test_offered_on_a_popup_returns_its_values_and_leaves_it_closed():
    with _popup_page(ids=True) as browser:
        assert browser.offered(Chooser.who) == ["", "u-ana", "u-bo"]
        assert browser.page.get_attribute("#who", "aria-expanded") == "false"
        assert browser.labels(Chooser.who) == ["Anyone", "ana", "bo"]
        assert browser.page.get_attribute("#who", "aria-expanded") == "false"


def test_a_derived_list_drawn_as_a_popup_passes_when_the_page_shows_what_the_book_derives():
    with _popup_page() as browser:
        browser.fill(Popup.who, "ana")
        assert browser.list_faults() == []
        assert browser.lists_read() == {"Popup.who"}


def test_a_derived_list_drawn_as_a_popup_fails_the_step_when_the_page_shows_another_order():
    with _popup_page(sort=False) as browser:
        browser.fill(Popup.who, "ana")
        assert browser.list_faults() == [
            "the list Popup.who shows ['Anyone', 'bo', 'ana'], the book derives ['Anyone', 'ana', 'bo']"]


class _Spoken:
    """A stand-in page that records the language each step is performed in, and answers as the model does."""

    name = "spoken"

    def __init__(self, service, lang: str, today) -> None:
        self.service, self.lang, self.today = service, lang, today
        self.model = service.new_model(today)
        self.sent: list[tuple[str, str]] = []

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def reset(self) -> None:
        return None

    def set_lang(self, lang: str) -> None:
        self.lang = lang

    def fresh(self):
        self.model = self.service.new_model(self.today)
        return self.service.new_model(self.today)

    def perform(self, step):
        self.sent.append((type(step).__name__, self.lang))
        return self.model.perform(step)

    def rows(self):
        return self.model.rows()


def _played_after_a_french_journey(monkeypatch: pytest.MonkeyPatch, silence: str, only: str):
    from datetime import date

    from ostler.book import inputs

    service = module("services.web.service").service
    assert service.language == "en"
    page = _Spoken(service, "fr", date(2026, 1, 5))
    if silence == "twins":
        monkeypatch.setattr(inputs, "twin_classes", lambda call, model: [])
    inputs.play(service, page, page.fresh, frozenset({only}), date(2026, 1, 5))
    return page


def test_the_input_classes_of_a_book_play_in_the_service_language_when_its_last_journey_played_in_another(monkeypatch: pytest.MonkeyPatch):
    page = _played_after_a_french_journey(monkeypatch, "twins", "AddTodo")
    assert page.sent
    assert {lang for _, lang in page.sent} == {"en"}


def test_the_twins_of_a_book_play_in_the_service_language_when_its_last_journey_played_in_another(monkeypatch: pytest.MonkeyPatch):
    from ostler.book import inputs

    monkeypatch.setattr(inputs, "one", lambda *args, **kwargs: (inputs.Sent(args[1], inputs.InputClass("", "", "", None, False), True), None))
    page = _played_after_a_french_journey(monkeypatch, "classes", "AddTodo")
    assert page.sent
    assert {lang for _, lang in page.sent} == {"en"}


def test_a_base_arranged_by_a_journey_of_another_language_ends_in_the_service_language():
    from datetime import date

    from ostler.book import inputs

    service = module("services.web.service").service
    french = next(j for j in service.journeys if j.lang == "fr")
    page = _Spoken(service, "en", date(2026, 1, 5))
    inputs._journey_base(french, 1, service.language)(page, page.fresh)
    assert page.sent
    assert {lang for _, lang in page.sent} == {"fr"}
    assert page.lang == "en"


def _unreachable_class():
    import dataclasses

    from ostler.book import Refusal, Refusals
    from ostler.book.inputs import classes, vary

    service = module("services.web.service").service
    service = dataclasses.replace(service, refusals=Refusals(malformed=Refusal("malformed", 422)))
    add, found = _todo_base()
    base = found[add]
    chosen = next(c for c in classes(base.call, base.before, None) if c.label == "due_on malformed date")
    return service, base, chosen, vary(base.call, chosen)


class _Refusing(Quiet):
    def __init__(self, rows) -> None:
        self.held = rows

    def perform(self, step):
        from ostler.book import CannotReach

        raise CannotReach("the page does not take 'not a date'")

    def rows(self):
        return self.held


def test_an_input_the_page_cannot_take_passes_as_unreachable_when_the_book_refuses_it_by_a_default_key(monkeypatch: pytest.MonkeyPatch):
    from ostler.book import inputs
    from ostler.book.inputs import judge

    monkeypatch.setattr(inputs, "predicted", lambda call, model: None)
    service, base, chosen, call = _unreachable_class()
    sent = judge(service, call, chosen, base.before, _Refusing(base.before.rows()))
    assert sent.ok, sent.note


def test_the_same_input_still_fails_when_the_book_expects_it_to_save(monkeypatch: pytest.MonkeyPatch):
    import dataclasses

    from ostler.book import Diverges, inputs
    from ostler.book.inputs import judge

    monkeypatch.setattr(inputs, "predicted", lambda call, model: None)
    service, base, chosen, call = _unreachable_class()
    service = dataclasses.replace(service, refusals=type(service.refusals)(), diverges=(Diverges(type(call), chosen.label, why="the app takes any day"),))
    sent = judge(service, call, chosen, base.before, _Refusing(base.before.rows()))
    assert not sent.ok
    assert not sent.diverged
