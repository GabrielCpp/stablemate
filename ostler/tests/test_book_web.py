"""The browser surface of the book runtime, and the todo web book of `fixtures/book_todo` played headless against the stand-in app and its page."""

from __future__ import annotations

import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from book_todo import run_book, module
from ostler.book import Browser, BookError, Screen, T
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
    nick = Field(None, T("Name", "Nom"))
    who = Select(None, T("Who", "Qui"), (T("Nobody", "Personne"), T("ana", "ana")))
    go = Button(None, T("Go", "Aller"))
    agree = Check(None, T("Agree", "D'accord"))
    echo = Text("echo")
    pick = Button(None, T("Pick", "Choisir"), per_row=True)


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
    found = Browser(page, lang_query=None)
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
