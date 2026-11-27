"""Reading the labels of a select judges the list the book states for it, as picking in it does."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from ostler.book import Browser, Screen, T
from ostler.book.wanted import request
from ostler.book.screen import Lists, Select

PAGE = (
    '<!doctype html><html><body><select data-testid="assignee"></select><script>'
    "fetch('/users').then(r => r.json()).then(users => {"
    "const select = document.querySelector('select');"
    "users.forEach(u => select.add(new Option(u)));"
    "select.dataset.ready = 'yes'; });</script></body></html>")


def by_name(users: list[str]) -> list[str]:
    """the names of the users, in the order served"""
    return users


def without_the_last(users: list[str]) -> list[str]:
    """the names of the users but the last"""
    return users[:-1]


def screen_of(derived: Any) -> Any:
    class Board(Screen):
        assignee = Select("assignee", T(en="Assignee"), lists=Lists(given=request("GET", "/users"), derived=derived))

    return Board


@contextmanager
def _page(users: list[str]) -> Iterator[Browser]:
    def answer(route: Any) -> None:
        if route.request.url.endswith("/users"):
            route.fulfill(content_type="application/json", body=json.dumps(users))
        else:
            route.fulfill(content_type="text/html", body=PAGE)

    found = Browser("http://board.test", "en", lang_query=None)
    found.start()
    found.context.route("**/*", answer)
    try:
        yield found
    finally:
        found.stop()


def _labels(browser: Browser, screen: Any) -> list[str]:
    browser.feeding((screen,))
    browser.open("/")
    browser.page.wait_for_selector('[data-testid="assignee"][data-ready="yes"]')
    return browser.labels(screen.assignee)


def test_reading_the_labels_of_a_select_judges_its_list_and_counts_it_as_read():
    screen = screen_of(by_name)
    with _page(["Ana", "Bo"]) as browser:
        assert _labels(browser, screen) == ["Ana", "Bo"]
        assert browser.list_faults() == []
        assert browser.claims_judged() == {"Board.assignee": {"derived"}}


def test_reading_the_labels_of_a_select_fails_the_step_when_the_list_differs_from_what_the_book_derives():
    screen = screen_of(without_the_last)
    with _page(["Ana", "Bo"]) as browser:
        _labels(browser, screen)
        assert browser.list_faults() == ["the list Board.assignee shows ['Ana', 'Bo'], the book derives ['Ana']"]
