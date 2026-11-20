"""A list whose data the app's own server hands the page, on the SvelteKit app of `fixtures/book_todo/kit`: the decoding of what the server hands, the list judged on a first visit and after a navigation, and the kit book played against the app."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from book_todo import FIXTURE, module, run_book
from ostler.book import Browser, BookError, Screen, action, handed
from ostler.book.pagedata import decode, on_route
from ostler.book.screen import Lists, Select

if shutil.which("node") is None:
    pytest.skip("node is not on PATH, and the kit app of this fixture runs on it", allow_module_level=True)

BUILD = FIXTURE / "kit" / "build" / "index.js"
SHARED = [{"when": 1, "tags": 2, "by": 5, "gone": -1, "first": 8, "second": 8, "big": 10, "nan": -3, "inf": -4,
           "neg": -6, "re": 11, "plain": 12}, ["Date", "2026-11-04T10:00:00.000Z"], ["Set", 3, 4], "a", "b",
          ["Map", 6, 7], "x", 1, {"name": 9}, "bo", ["BigInt", "12"], ["RegExp", "ab+c", "gi"], [7, -1, 13], 3]


def _answer(*nodes: object) -> str:
    return json.dumps({"type": "data", "nodes": list(nodes)}) + "\n"


def _data(flat: list) -> dict:
    return {"type": "data", "data": flat, "uses": {}}


def test_the_committed_build_names_no_file_outside_the_kit():
    """The bundler names each module's source file in a comment, and a rebuild against node_modules outside its folder writes the builder's own path into a public repo."""
    escaped = [
        f"{path.relative_to(FIXTURE)}: {line}"
        for path in sorted((FIXTURE / "kit" / "build").rglob("*.js"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(("// ../", "// /"))
    ]

    assert escaped == []


def test_a_page_s_data_decodes_dates_sets_maps_undefined_and_a_value_referenced_twice():
    got = decode(_answer(None, _data(SHARED)))
    assert got["when"] == "2026-11-04T10:00:00.000Z"
    assert got["tags"] == ["a", "b"]
    assert got["by"] == {"x": 1}
    assert got["gone"] is None
    assert got["first"] == {"name": "bo"}
    assert got["first"] is got["second"]
    assert got["big"] == 12
    assert got["re"] == "ab+c"
    assert got["plain"] == [1, None, 3]
    assert got["nan"] != got["nan"]
    assert got["inf"] == float("inf")


def test_layout_and_page_data_merge_with_the_page_winning():
    layout = _data([{"users": 1, "title": 4}, [2], {"name": 3}, "bo", "layout"])
    page = _data([{"title": 1}, "page"])
    assert decode(_answer(layout, page)) == {"users": [{"name": "bo"}], "title": "page"}


def test_a_skipped_node_is_left_out_of_the_page_s_data():
    page = _data([{"title": 1}, "page"])
    assert decode(_answer({"type": "skip"}, page, None)) == {"title": "page"}


def test_an_error_node_is_refused_with_what_the_run_met():
    boom = {"type": "error", "error": {"message": "Internal Error"}, "status": 500}
    with pytest.raises(BookError, match="a load of the page failed: .*Internal Error"):
        decode(_answer(None, boom))


def test_a_streamed_answer_is_refused_with_what_the_run_met():
    streamed = _answer(None, _data([{"title": 1}, "page"])) + '{"type":"chunk","id":1,"data":"1"}\n'
    with pytest.raises(BookError, match="streamed its data in 2 lines"):
        decode(streamed)


def test_a_redirect_is_refused_with_where_it_led():
    with pytest.raises(BookError, match="redirected to '/login'"):
        decode(json.dumps({"type": "redirect", "location": "/login"}))


@pytest.mark.parametrize("route, path, on", [
    ("/", "/", True), ("/assign", "/assign", True), ("/assign", "/", False), ("/tickets/[id]", "/tickets/7", True),
    ("/tickets/[id]", "/tickets", False), ("/(app)/tickets", "/tickets", True), ("/docs/[...rest]", "/docs/a/b", True),
])
def test_a_path_is_on_a_route_the_way_sveltekit_spells_it(route: str, path: str, on: bool):
    assert on_route(route, path) is on


def test_a_path_with_more_segments_than_its_route_is_not_on_it():
    assert not on_route("/assign", "/assign/extra")


def test_a_path_with_a_suffix_after_its_route_is_not_on_it():
    assert not on_route("/assign", "/assignment")


def test_a_route_parameter_takes_exactly_one_segment():
    assert on_route("/tickets/[id]", "/tickets/7")
    assert not on_route("/tickets/[id]", "/tickets/7/edit")


def test_a_rest_parameter_takes_no_segment_as_well_as_several():
    assert on_route("/docs/[...rest]", "/docs")
    assert on_route("/docs/[...rest]", "/docs/a")
    assert on_route("/docs/[...rest]", "/docs/a/b")


def test_a_trailing_slash_leaves_a_path_on_its_route():
    assert on_route("/assign", "/assign/")
    assert on_route("/tickets/[id]", "/tickets/7/")


class _Request:
    def __init__(self, method: str, url: str):
        self.method = method
        self.url = url


class _Response:
    def __init__(self, method: str, url: str):
        self.request = _Request(method, url)


def test_a_form_action_matches_the_post_to_its_page_that_names_it():
    assert action("/", "add")(_Response("POST", "http://app.test/?/add"))
    assert action("/tickets/[id]", "close")(_Response("POST", "http://app.test/tickets/7?/close"))


def test_a_form_action_matches_no_get_to_the_same_page():
    assert not action("/", "add")(_Response("GET", "http://app.test/?/add"))


def test_a_form_action_matches_no_post_to_another_page():
    assert not action("/", "add")(_Response("POST", "http://app.test/other?/add"))


def test_a_form_action_matches_no_post_that_names_another_action():
    assert not action("/", "add")(_Response("POST", "http://app.test/?/remove"))


def test_a_form_action_matches_no_post_that_names_no_action():
    assert not action("/", "add")(_Response("POST", "http://app.test/"))


def _free_port() -> int:
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        return taken.getsockname()[1]


@contextmanager
def _kit(bug: str | None = None) -> Iterator[tuple]:
    api = module("app").TodoServer().start()
    port = _free_port()
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "ORIGIN": f"http://127.0.0.1:{port}", "TODO_API": api.url}
    if bug:
        env["PUBLIC_KIT_BUG"] = bug
    node = subprocess.Popen(["node", str(BUILD)], env=env, stdout=subprocess.PIPE, text=True)
    try:
        assert node.stdout is not None
        line = node.stdout.readline()
        assert "Listening on" in line, f"the kit app said {line!r} and stopped"
        yield api, port
    finally:
        node.terminate()
        node.wait()
        if node.stdout is not None:
            node.stdout.close()
        api.stop()


@pytest.fixture
def kit() -> Iterator[tuple]:
    with _kit() as running:
        yield running


def _screens():
    return module("services.kit.screens")


@contextmanager
def _browser(port: int, screens: tuple | None = None) -> Iterator[Browser]:
    found = Browser(f"http://127.0.0.1:{port}", "en", lang_query=None)
    found.feeding(screens or _screens().ALL)
    found.start()
    found.watching("/api")
    try:
        yield found
    finally:
        found.stop()


def _home(browser: Browser) -> None:
    browser.open("/")
    browser.page.wait_for_selector('[data-testid="add-form"][data-ready="true"]')


def _assign(browser: Browser) -> None:
    browser.open("/assign")
    _assigned(browser)


def _assigned(browser: Browser) -> None:
    browser.page.wait_for_function("() => document.querySelector('[data-testid=\"assignee\"]').options.length > 1")


def _by_link(browser: Browser, link, url: str) -> None:
    browser.press(link)
    browser.page.wait_for_url(url)


def _after_a_round_trip(browser: Browser) -> None:
    screens = _screens()
    _home(browser)
    _by_link(browser, screens.Home.to_assign, "**/assign")
    _assigned(browser)
    _by_link(browser, screens.Assign.back, "**/")
    browser.page.wait_for_selector('[data-testid="add-form"][data-ready="true"]')


OWNER_FAULT = "the list Home.owner shows ['Nobody', 'bo', 'ana'], the book derives ['Nobody', 'ana', 'bo']"
ASSIGNEE_FAULT = "the list Assign.assignee shows ['Anyone', 'bo', 'ana'], the book derives ['Anyone', 'ana', 'bo']"


def test_a_list_handed_with_the_page_passes_on_a_first_visit_when_the_page_shows_what_the_book_derives(kit):
    with _browser(kit[1]) as browser:
        _home(browser)
        browser.fill(_screens().Home.owner, "ana")
        assert browser.list_faults() == []
        assert browser.lists_read() == {"Home.owner"}


def test_a_list_handed_with_the_page_fails_on_a_first_visit_when_the_page_leaves_the_users_in_the_order_handed():
    with _kit("handed-order") as (_, port), _browser(port) as browser:
        _home(browser)
        browser.fill(_screens().Home.owner, "ana")
        assert browser.list_faults() == [OWNER_FAULT]


def test_a_list_handed_with_the_page_passes_after_a_navigation_inside_the_app(kit):
    with _browser(kit[1]) as browser:
        _after_a_round_trip(browser)
        browser.fill(_screens().Home.owner, "ana")
        assert browser.list_faults() == []


def test_a_list_handed_with_the_page_fails_after_a_navigation_when_the_page_leaves_the_users_in_the_order_handed():
    with _kit("handed-order") as (_, port), _browser(port) as browser:
        _after_a_round_trip(browser)
        browser.fill(_screens().Home.owner, "ana")
        assert browser.list_faults() == [OWNER_FAULT]


def test_a_list_fetched_through_the_gateway_passes_on_a_first_visit(kit):
    with _browser(kit[1]) as browser:
        _assign(browser)
        browser.fill(_screens().Assign.assignee, "ana")
        assert browser.list_faults() == []


def test_a_list_fetched_through_the_gateway_fails_on_a_first_visit_when_the_page_leaves_the_users_in_the_order_received():
    with _kit("fetched-order") as (_, port), _browser(port) as browser:
        _assign(browser)
        browser.fill(_screens().Assign.assignee, "ana")
        assert browser.list_faults() == [ASSIGNEE_FAULT]


def test_a_list_fetched_through_the_gateway_passes_after_a_navigation(kit):
    screens = _screens()
    with _browser(kit[1]) as browser:
        _home(browser)
        _by_link(browser, screens.Home.to_assign, "**/assign")
        _assigned(browser)
        browser.fill(screens.Assign.assignee, "bo")
        assert browser.list_faults() == []


def test_a_list_fetched_through_the_gateway_fails_after_a_navigation_when_the_page_leaves_the_users_in_the_order_received():
    screens = _screens()
    with _kit("fetched-order") as (_, port), _browser(port) as browser:
        _home(browser)
        _by_link(browser, screens.Home.to_assign, "**/assign")
        _assigned(browser)
        browser.fill(screens.Assign.assignee, "bo")
        assert browser.list_faults() == [ASSIGNEE_FAULT]


def test_a_handed_list_read_on_a_page_that_is_not_its_route_fails_and_names_the_list_the_path_and_the_route(kit):
    class Elsewhere(Screen):
        owner = Select("owner", "Owner", lists=Lists(given=handed("/assign"), derived=_by_name))

    with _browser(kit[1], (Elsewhere,)) as browser:
        _home(browser)
        browser.fill(Elsewhere.owner, "ana")
        assert browser.list_faults() == [
            "the list Elsewhere.owner is data handed with the page of /assign, and the page open is at /, not on /assign"]


def _by_name(data):
    """the users handed"""
    return [u["name"] for u in data["users"]]


def test_a_handed_list_the_server_cannot_hand_is_a_fault_that_says_what_the_server_answered(kit):
    class Missing(Screen):
        owner = Select("owner", "Owner", lists=Lists(given=handed("/[slug]"), derived=_by_name))

    with _browser(kit[1], (Missing,)) as browser:
        browser.open("/nowhere")
        browser.page.evaluate("""document.body.insertAdjacentHTML('beforeend',
            '<select data-testid="owner"><option>x</option></select>')""")
        browser.fill(Missing.owner, "x")
        [fault] = browser.list_faults()
        assert fault.startswith("the list Missing.owner is data handed with the page of /[slug], and the app's server answered 404")


def test_a_step_that_adds_a_todo_through_the_form_action_waits_on_its_answer_and_passes(kit, tmp_path: Path):
    api, port = kit
    done = _play(api, port, tmp_path, "AnOwnerIsPickedOnAFirstVisit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 pass, 0 known defects, 0 fail" in done.stdout


def test_a_request_to_the_app_s_api_that_no_screen_declares_fails_the_step(tmp_path: Path):
    with _kit("stray") as (api, port):
        done = _play(api, port, tmp_path, "AnAssigneeIsPickedOnAFirstVisit")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the page sent a request no screen declares: GET /api/todos" in done.stdout


def test_a_run_on_the_correct_app_names_no_navigation_data_request_and_no_form_action_as_a_stray(kit):
    screens = _screens()
    with _browser(kit[1]) as browser:
        _home(browser)
        browser.fill(screens.Home.title, "Buy milk")
        with browser.answered(action("/", "add")):
            browser.press(screens.Home.add)
        _by_link(browser, screens.Home.to_assign, "**/assign")
        _assigned(browser)
        _by_link(browser, screens.Assign.back, "**/")
        sent = [f"{r.method} {r.url.split('/', 3)[3]}" for r in browser.taken()]
    assert sent == ["GET api/users"]


def test_a_form_action_answers_a_post_to_the_page_with_its_name_in_the_query(kit):
    screens = _screens()
    with _browser(kit[1]) as browser:
        _home(browser)
        browser.fill(screens.Home.title, "Buy milk")
        with browser.answered(action("/", "add")) as got:
            browser.press(screens.Home.add)
        assert got.response.request.method == "POST"
        assert "?/add" in got.response.request.url
        assert got.json()["type"] == "success"


def _play(api, port: int, tmp_path: Path, *only: str):
    arguments = ["run", "services.kit", "--no-stack", "--out", str(tmp_path / "out")]
    for journey in only:
        arguments += ["--journey", journey, "--partial"]
    return run_book(arguments, api.port, kit=port)


def test_the_kit_book_is_green_on_the_correct_app(kit, tmp_path: Path):
    api, port = kit
    done = _play(api, port, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "4 pass, 0 known defects, 0 fail" in done.stdout
    assert "no screen declares" not in done.stdout


@pytest.mark.parametrize("bug, journey, fault", [
    ("handed-order", "AnOwnerIsPickedOnAFirstVisit", OWNER_FAULT),
    ("handed-order", "AnOwnerIsPickedAfterANavigation", OWNER_FAULT),
    ("fetched-order", "AnAssigneeIsPickedOnAFirstVisit", ASSIGNEE_FAULT),
    ("fetched-order", "AnAssigneeIsPickedAfterANavigation", ASSIGNEE_FAULT),
])
def test_the_kit_book_is_red_on_a_planted_order_bug_and_names_the_failing_step(bug: str, journey: str, fault: str, tmp_path: Path):
    with _kit(bug) as (api, port):
        done = _play(api, port, tmp_path, journey)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"FAIL  {journey}" in done.stdout
    assert fault in done.stdout


def test_the_description_of_a_screen_says_its_list_is_handed_with_the_page_of_its_route():
    described = _screens().Home.describe("en")
    assert "from the data handed with the page of /" in described
    assert "the users the page was handed, by name" in described

