"""A list whose entries the book derives, played headless against a stand-in page: the declaration refused, the description a screen gives, and a pick judged in a select and in a popup."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator, cast

import pytest

from ostler.book import Browser, BookError, Screen, T
from ostler.book.model import Model
from ostler.book.surface import Surface
from ostler.book.wanted import request
from ostler.book.screen import Lists, Select

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
