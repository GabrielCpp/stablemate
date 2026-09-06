"""The CDP fill: target selection, the safety refusals, and what it reports.

No browser is started. The session is the seam — :class:`~saddlebag.browser.CdpSession`
is a Protocol precisely so a recorder can stand in for one, which is also what lets a
test assert the thing that matters most: that the value goes out over ``Input.insertText``
and comes back only as a length.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from saddlebag import browser


class FakeSession:
    """Records commands and answers them from a scripted page state."""

    def __init__(self, *, found: bool = True, editable: bool = True, length: int | None = None) -> None:
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self._found = found
        self._editable = editable
        self._length = length
        self.typed: str | None = None

    def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.commands.append((method, params))
        if method == "Input.insertText":
            self.typed = params["text"]
            return {}
        expression = params["expression"]
        if "el.focus()" in expression:
            value: Any = {"found": self._found, "editable": self._editable, "tag": "DIV", "type": None}
            if not self._found:
                value = {"found": False}
            return {"result": {"value": value}}
        typed = len(self.typed or "")
        return {"result": {"value": typed if self._length is None else self._length}}


def target(url: str, id_: str = "t") -> browser.Target:
    return browser.Target(id=id_, url=url, title="", websocket_url=f"ws://127.0.0.1:9222/devtools/page/{id_}")


# -- the loopback refusal ---------------------------------------------------


@pytest.mark.parametrize("endpoint", ["http://192.168.1.10:9222", "http://browser.example.com:9222", "http://"])
def test_a_non_loopback_endpoint_is_refused(endpoint: str) -> None:
    """A remote DevTools port is an unauthenticated password drop, not a deployment."""
    with pytest.raises(browser.BrowserError, match="loopback"):
        browser.require_loopback(endpoint)


@pytest.mark.parametrize("endpoint", ["http://127.0.0.1:9222", "http://localhost:9222", "http://[::1]:9222"])
def test_loopback_endpoints_are_allowed(endpoint: str) -> None:
    browser.require_loopback(endpoint)


# -- choosing the page ------------------------------------------------------


def test_selects_the_only_page_matching_the_filter() -> None:
    pages = (target("https://github.com/login", "a"), target("https://example.com/", "b"))
    assert browser.select_target(pages, "github.com").id == "a"


def test_several_matching_pages_is_an_error_rather_than_a_guess() -> None:
    """Typing a password into whichever tab sorted first is unrecoverable and silent."""
    pages = (target("https://github.com/login", "a"), target("https://github.com/session", "b"))
    with pytest.raises(browser.BrowserError, match="2 pages match"):
        browser.select_target(pages, "github.com")


def test_no_matching_page_lists_what_is_open() -> None:
    with pytest.raises(browser.BrowserError, match="example.com"):
        browser.select_target((target("https://example.com/"),), "github.com")


def test_no_pages_at_all_is_an_error() -> None:
    with pytest.raises(browser.BrowserError, match="no inspectable pages"):
        browser.select_target((), None)


# -- the fill itself --------------------------------------------------------


def test_types_the_value_and_reports_only_its_length() -> None:
    session = FakeSession()
    assert browser.fill(session, "input[name='password']", "hunter2") == 7
    assert session.typed == "hunter2"
    methods = [method for method, _ in session.commands]
    assert methods == ["Runtime.evaluate", "Input.insertText", "Runtime.evaluate"]


def test_the_secret_never_appears_in_an_evaluated_expression() -> None:
    """The value rides ``Input.insertText`` alone.

    Interpolating it into a ``Runtime.evaluate`` would put the password in the
    browser's own protocol log, where a DevTools window replays it in cleartext.
    """
    session = FakeSession()
    browser.fill(session, "#pw", "hunter2")
    for method, params in session.commands:
        if method == "Runtime.evaluate":
            assert "hunter2" not in params["expression"]


def test_the_selector_is_json_encoded_into_the_expression() -> None:
    """A selector carrying a quote must not be able to close the string it sits in."""
    session = FakeSession()
    browser.fill(session, "input[name='password']", "x")
    expression = session.commands[0][1]["expression"]
    assert json.dumps("input[name='password']") in expression


def test_a_selector_that_matches_nothing_names_the_selector() -> None:
    session = FakeSession(found=False)
    with pytest.raises(browser.BrowserError, match="#missing"):
        browser.fill(session, "#missing", "x")
    assert session.typed is None, "nothing may be typed once the target is known to be absent"


def test_a_non_editable_match_is_refused_before_anything_is_typed() -> None:
    session = FakeSession(editable=False)
    with pytest.raises(browser.BrowserError, match="cannot hold typed text"):
        browser.fill(session, "div.field", "x")
    assert session.typed is None


def test_a_field_still_empty_afterwards_is_an_error() -> None:
    """Read-only inputs accept the insert silently; only the read-back catches it."""
    session = FakeSession(length=0)
    with pytest.raises(browser.BrowserError, match="still empty"):
        browser.fill(session, "#pw", "hunter2")


def test_a_truncated_field_is_reported_but_not_bisectable(caplog: pytest.LogCaptureFixture) -> None:
    """The warning carries two lengths and no substring of the value."""
    session = FakeSession(length=3)
    assert browser.fill(session, "#pw", "hunter2") == 3
    assert "hunter2" not in caplog.text
    assert "3" in caplog.text
