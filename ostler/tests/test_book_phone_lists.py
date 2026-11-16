"""A list read on a phone, and a list fed by asking a backend through its book."""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Iterator, cast

import pytest

from book_todo import module
from ostler.book import Bearer, BookError, Browser, CannotReach, Device, Environment, Screen, T, asked, handed, in_order, no_repeat, request
from ostler.book.cast import Actor
from ostler.book.model import Model
from ostler.book.surface import Surface
from ostler.book.cli import fresh
from ostler.book.owners import Owners
from ostler.book.runner import asked_feeds, hand_over, perform
from ostler.book.screen import Lists, Select
from test_book_mobile import Calls, FakeScreen, node
from test_book_web import _stack, _stop

FindTodos = module("services.api.endpoints").FindTodos
TodoApi = module("services.api.surface").TodoApi


def titles(todos):
    """the titles of the todos asked, in the order the app answered"""
    return [todo["title"] for todo in todos]


def assignees(todos):
    """the owners of the todos asked, by name"""
    return sorted({todo["assignee"] for todo in todos if todo["assignee"]})


class Chooser(Screen):
    who = Select("who", T(en="Who", fr="Qui"), lists=Lists(head=("Anyone",), given=asked(FindTodos), derived=titles))


class Ordered(Screen):
    who = Select("who", T(en="Who", fr="Qui"), lists=Lists(head=("Anyone",), entries=(in_order(), no_repeat())))


class Preset(Screen):
    who = Select("who", T(en="Who", fr="Qui"), lists=Lists(head=("Anyone",), picked="Anyone"))


class Received(Screen):
    who = Select("who", T(en="Who", fr="Qui"), lists=Lists(head=("Anyone",), given=request("GET", "/todos"), derived=titles))


class Handed(Screen):
    who = Select("who", T(en="Who", fr="Qui"), lists=Lists(head=("Anyone",), given=handed("/todos"), derived=titles))


class Pick:
    screen = Chooser

    def __init__(self, by: Actor | None = None) -> None:
        self.by = by or Actor("ana")


def view(*entries: str, selected: str = "Anyone", upside_down: bool = False) -> str:
    shown = [node("[0,0][1080,2400]", **{"class": "android.view.View"}),
             node("[40,300][1040,420]", **{"class": "android.widget.Button", "resource-id": "who", "text": selected})]
    for at, text in enumerate(entries):
        shown.append(node(f"[40,{500 + at * 120}][1040,{600 + at * 120}]", **{"class": "android.view.View", "accessibilityText": text}))
    return json.dumps({"attributes": {}, "children": shown[:2] + (shown[:1:-1] if upside_down else shown[2:])})


class Phone(Calls):
    """A phone whose list opens when the select is tapped and closes on Android back."""

    def __init__(self, closed: str, opened: str) -> None:
        super().__init__()
        self.closed, self.opened = closed, opened
        self.shown = closed

    def run(self, argv: list[str], **kwargs: object):
        if argv[-4:-2] == ["input", "tap"]:
            self.shown = self.opened if argv[-2:] == ["540", "360"] else self.closed
        if argv[-3:] == ["input", "keyevent", "4"]:
            self.shown = self.closed
        return super().run(argv, **kwargs)

    def taps(self) -> list[tuple[str, str]]:
        return [(argv[-2], argv[-1]) for argv in self.argv if argv[-4:-2] == ["input", "tap"]]


def phone(monkeypatch: pytest.MonkeyPatch, screen: type[Screen], *entries: str, selected: str = "Anyone") -> tuple[Device, Phone]:
    import subprocess

    calls = Phone(view(selected=selected), view(*entries, selected=selected))
    monkeypatch.setattr(subprocess, "run", calls.run)
    monkeypatch.setattr("ostler.book.device.load_harness_module", lambda _name: FakeScreen(calls))
    device = Device("com.example.app", "en", timeout=0.0)
    device.feeding((screen,))
    return device, calls


def add(server: Any, title: str, assignee: str | None = None) -> None:
    body = json.dumps({"title": title, **({"assignee": assignee} if assignee else {})}).encode()
    made = urllib.request.Request(f"{server.url}/todos", body, {"Authorization": "Bearer test-token", "Content-Type": "application/json"})
    urllib.request.urlopen(made).read()


@pytest.fixture
def backend() -> Iterator[tuple[Any, list[Any]]]:
    server = module("app").TodoServer().start()
    environment = Environment("local", {"api": server.url})
    sentas: list[Any] = []

    class Recording(TodoApi):
        def __init__(self, environment: Environment) -> None:
            super().__init__(environment)
            for person in ("ana", "bo"):
                self.client.held[(Actor(person), Bearer())] = "test-token"

        def send(self, call: Any) -> Any:
            sentas.append(call.by)
            return super().send(call)

    Owners.begin(environment, lambda service: Recording(environment), fresh)
    yield server, sentas
    Owners.close()
    server.stop()


def test_the_phone_reader_picks_the_entry_whose_text_is_the_value_after_reading_the_entries_that_appeared(monkeypatch, backend):
    server, _ = backend
    add(server, "first")
    add(server, "second")
    device, calls = phone(monkeypatch, Chooser, "Anyone", "second", "first")
    device.expecting({}, asked_feeds(Pick()))

    device.fill(Chooser.who, "first")

    assert calls.taps() == [("540", "360"), ("540", "790")]
    assert device.list_faults() == []
    assert device.lists_read() == {"Chooser.who"}


def test_a_value_the_phone_list_does_not_show_is_closed_again_and_cannot_be_reached(monkeypatch):
    device, calls = phone(monkeypatch, Ordered, "Anyone", "ana", "bo")

    with pytest.raises(CannotReach, match=r"offers only \['Anyone', 'ana', 'bo'\]"):
        device.fill(Ordered.who, "zed")

    assert calls.argv[-1] == ["adb", "shell", "input", "keyevent", "4"]
    assert calls.taps() == [("540", "360")]
    assert calls.shown == calls.closed


def test_the_labels_of_a_phone_list_are_read_top_to_bottom_and_the_list_is_closed(monkeypatch):
    device, calls = phone(monkeypatch, Ordered, "Anyone", "ana", "bo")
    calls.opened = view("Anyone", "ana", "bo", upside_down=True)

    assert device.labels(Ordered.who) == ["Anyone", "ana", "bo"]
    assert calls.shown == calls.closed


def test_reading_the_labels_of_a_phone_list_judges_its_entry_rules(monkeypatch):
    device, calls = phone(monkeypatch, Ordered, "Anyone", "bo", "ana")
    calls.opened = view("Anyone", "bo", "ana", upside_down=True)

    assert device.labels(Ordered.who) == ["Anyone", "bo", "ana"]
    assert device.list_faults() == ["the list Ordered.who breaks \"in order\": 'ana' comes after 'bo'"]


def test_a_phone_list_derived_from_the_asked_feed_passes_when_it_shows_what_the_book_derives(monkeypatch, backend):
    server, _ = backend
    add(server, "first")
    add(server, "second")
    device, _ = phone(monkeypatch, Chooser, "Anyone", "second", "first")
    device.expecting({}, asked_feeds(Pick()))

    device.fill(Chooser.who, "first")

    assert device.list_faults() == []


def test_a_phone_list_whose_entries_come_in_another_order_than_the_asked_feed_fails_naming_the_list(monkeypatch, backend):
    server, _ = backend
    add(server, "first")
    add(server, "second")
    device, _ = phone(monkeypatch, Chooser, "Anyone", "first", "second")
    device.expecting({}, asked_feeds(Pick()))

    device.fill(Chooser.who, "first")

    assert device.list_faults() == ["the list Chooser.who shows ['Anyone', 'first', 'second'], the book derives ['Anyone', 'second', 'first']"]


def test_the_entry_rules_are_judged_on_a_phone_list(monkeypatch):
    device, _ = phone(monkeypatch, Ordered, "Anyone", "bo", "ana", "ana")

    device.fill(Ordered.who, "bo")

    assert device.list_faults() == [
        "the list Ordered.who breaks \"in order\": 'ana' comes after 'bo'",
        "the list Ordered.who breaks \"no repeat\": 'ana' is shown 2 times"]
    assert device.claims_judged() == {"Ordered.who": frozenset({"entries"})}


def test_the_entry_selected_before_the_pick_is_judged_on_a_phone_list(monkeypatch):
    device, _ = phone(monkeypatch, Preset, "Anyone", "ana", selected="ana")

    device.fill(Preset.who, "ana")

    assert device.list_faults() == ["the list Preset.who has 'ana' selected before the pick, the book says 'Anyone'"]


def test_the_selected_entry_is_judged_again_after_the_app_is_launched(monkeypatch):
    device, _ = phone(monkeypatch, Preset, "Anyone", "ana", selected="ana")
    device.fill(Preset.who, "ana")
    device.list_faults()
    device.fill(Preset.who, "ana")
    assert device.list_faults() == []

    device.launch()
    device.fill(Preset.who, "ana")

    assert len(device.list_faults()) == 1


@pytest.mark.parametrize("screen, fed", [(Received, "GET /todos"), (Handed, "data handed with the page of /todos")])
def test_a_phone_list_fed_by_what_the_app_received_is_a_fault_that_says_the_phone_cannot_see_it(monkeypatch, screen, fed):
    device, _ = phone(monkeypatch, screen, "Anyone", "ana")

    device.fill(screen.who, "ana")

    assert device.list_faults() == [
        f"the list {screen.__name__}.who is {fed}, and a phone cannot see what the app received: "
        "state the list as asked(<an endpoint of the backend's book>)"]


def test_the_asked_call_is_sent_as_the_person_taking_the_step(backend):
    _, sentas = backend
    by = Actor("bo")

    asked_feeds(Pick(by))

    assert sentas == [by]


def test_an_asked_feed_whose_owner_refuses_is_a_fault_naming_the_call_and_the_refusal(monkeypatch, backend):
    server, _ = backend
    down = urllib.request.Request(f"{server.url}/admin/store", b'{"down": true}', {"Content-Type": "application/json"})
    urllib.request.urlopen(down).read()
    device, _ = phone(monkeypatch, Chooser, "Anyone", "first")
    device.expecting({}, asked_feeds(Pick()))

    device.fill(Chooser.who, "first")

    [fault] = device.list_faults()
    assert fault.startswith("the list Chooser.who is asked of FindTodos of services.api, and the owner services.api refused ")
    assert "GET /todos" in fault


def test_an_asked_feed_whose_owner_has_no_book_is_a_fault_naming_why(monkeypatch):
    device, _ = phone(monkeypatch, Chooser, "Anyone", "first")
    device.expecting({}, asked_feeds(Pick()))

    device.fill(Chooser.who, "first")

    [fault] = device.list_faults()
    assert fault.startswith("the list Chooser.who is asked of FindTodos of services.api, and ")
    assert "no run has begun" in fault


def test_a_pick_before_any_step_asked_the_feed_is_a_fault_that_says_so(monkeypatch):
    device, _ = phone(monkeypatch, Chooser, "Anyone", "first")

    device.fill(Chooser.who, "first")

    assert device.list_faults() == ["the list Chooser.who is asked of FindTodos of services.api, and no step asked it before this pick"]


def test_a_step_hands_the_surface_the_asked_feed_and_takes_it_back_after(monkeypatch, backend):
    server, _ = backend
    add(server, "first")
    handed_over: list[tuple[Any, ...]] = []

    class Watcher:
        name = "stub"

        def expecting(self, expectations: dict, asked: dict | None = None) -> None:
            handed_over.append((dict(expectations), dict(asked or {})))

    monkeypatch.setattr("ostler.book.runner.move", lambda *args: "moved")

    assert perform("pick", Pick(), cast(Model, None), cast(Surface, Watcher())) == "moved"

    assert [step[0] for step in handed_over] == [{}, {}]
    assert [t["title"] for t in handed_over[0][1]["Chooser.who"]] == ["first"]
    assert handed_over[1][1] == {}


def test_hand_over_leaves_a_surface_that_takes_no_asked_feed_with_the_expectations_alone():
    seen: list[dict] = []

    class Plain:
        def expecting(self, expectations: dict) -> None:
            seen.append(expectations)

    hand_over(cast(Surface, Plain()), {"a": ([], [])})

    assert seen == [{"a": ([], [])}]


@pytest.fixture
def page() -> Iterator[Any]:
    stack = _stack()
    yield stack
    _stop(stack)


class Filter(Screen):
    assignee = Select("list-assignee", T(en="Assignee", fr="Responsable"),
                      lists=Lists(head=("Anyone",), given=asked(FindTodos), derived=assignees))


class Filtering:
    screen = Filter
    by = Actor("ana")


def signed(environment: Environment) -> Any:
    surface = TodoApi(environment)
    surface.client.held[(Actor("ana"), Bearer())] = "test-token"
    return surface


def opened(stack: Any) -> Iterator[Browser]:
    api, web = stack
    environment = Environment("local", {"api": api.url})
    Owners.begin(environment, lambda service: signed(environment), fresh)
    browser = Browser(f"http://127.0.0.1:{web.port}", "en", lang_query=None)
    browser.feeding((Filter,))
    browser.start()
    try:
        browser.open("/")
        browser.page.wait_for_function("document.getElementById('list-assignee').options.length > 1")
        yield browser
    finally:
        browser.stop()
        Owners.close()


def test_the_asked_feed_judges_a_web_list_too(page):
    api, _ = page
    add(api, "one", "ana")
    add(api, "two", "bo")
    for browser in opened(page):
        browser.expecting({}, asked_feeds(Filtering()))
        browser.fill(Filter.assignee, "bo")
        assert browser.list_faults() == []
        assert browser.lists_read() == {"Filter.assignee"}


def test_the_asked_feed_fails_a_web_list_that_shows_what_the_backend_did_not_answer(page):
    api, _ = page
    add(api, "one", "ana")
    for browser in opened(page):
        browser.expecting({}, asked_feeds(Filtering()))
        browser.fill(Filter.assignee, "bo")
        assert browser.list_faults() == ["the list Filter.assignee shows ['Anyone', 'ana', 'bo'], the book derives ['Anyone', 'ana']"]


def test_the_description_of_a_screen_shows_the_asked_feed():
    described = Chooser.describe("en")

    assert "lists: 'Anyone', the titles of the todos asked, in the order the app answered, asked of FindTodos of services.api" in described


@pytest.mark.parametrize("given", [FindTodos(), "FindTodos", None, int])
def test_a_call_that_is_not_an_endpoint_class_is_refused_where_it_is_declared(given):
    with pytest.raises(BookError, match="asked names an endpoint class"):
        asked(given)
