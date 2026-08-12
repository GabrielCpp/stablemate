"""The shape of what a browser scenario records about the page it drove.

These are the diagnostics a plan asserts on, so their field names are contract. They live
in the harness now — inside the scenario's own process, where the page object is — but the
failures each one was written for are unchanged, which is why the cases came across whole.

The module is loaded by path: it is stdlib-plus-playwright and deliberately not importable
as `ostler.*`, because the interpreter that runs a scenario is the project's, not ostler's.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_SOURCE = (
    Path(__file__).resolve().parents[1] / "ostler/qa/harness/ostler_qa_browser.py"
)
_spec = importlib.util.spec_from_file_location("ostler_qa_browser_under_test", _SOURCE)
assert _spec is not None and _spec.loader is not None
ostler_qa_browser = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ostler_qa_browser)
Browser = ostler_qa_browser.Browser


def _browser(tmp_path: Path, at_ms: int = 0, **target: object) -> Any:
    declared = {"browser": None, "permissions": None, "recording": None, "viewport": None}
    declared.update(target)
    return Browser(
        SimpleNamespace(**declared),
        qa_dir=tmp_path,
        scenario_id="scenario",
        clock=lambda: at_ms,
        emit=lambda record: None,
    )


def test_a_chromium_context_is_granted_the_clipboard_by_default(tmp_path: Path) -> None:
    """A copy journey is only provable if the context can reach the clipboard.

    Chromium denies an ungranted permission instead of prompting, so
    ``navigator.clipboard.writeText()`` rejects; an app that catches that renders its
    failure branch with no console error, and the run blames the product for a harness
    default. Firefox and WebKit reject the clipboard permission names outright, so the
    default is Chromium's alone.
    """
    assert _browser(tmp_path).permissions() == ["clipboard-read", "clipboard-write"]
    assert _browser(tmp_path, browser="firefox").permissions() == []
    assert _browser(tmp_path, permissions=["geolocation"]).permissions() == ["geolocation"]
    assert _browser(tmp_path, permissions=[]).permissions() == [], (
        "an explicit empty list denies, it does not fall back"
    )


def test_every_console_message_is_kept_not_only_the_errors(tmp_path: Path) -> None:
    """A scenario that fails with an empty ``consoleErrors`` used to leave nothing to read,
    though the warning that explains it — a React hydration or key warning, levelled
    ``warn`` — was right there on the console and thrown away.
    """
    browser = _browser(tmp_path, at_ms=1500)
    browser._on_console(
        SimpleNamespace(
            type="warning",
            text="Each child in a list should have a unique key.",
            location={
                "url": "http://127.0.0.1:8099/app.js",
                "lineNumber": 12,
                "columnNumber": 4,
            },
        )
    )

    assert browser._console == [
        {
            "atMs": 1500,
            "type": "warning",
            "text": "Each child in a list should have a unique key.",
            "location": "http://127.0.0.1:8099/app.js:12:4",
        }
    ]
    assert browser._console_errors == [], "a warning is not an error"

    unplaced = _browser(tmp_path)
    unplaced._on_console(SimpleNamespace(type="log", text="ready", location=None))
    assert unplaced._console[0]["location"] == "", (
        "a message with no source location reports no location, not 'None:0:0'"
    )


def test_an_uncaught_exception_is_recorded_at_all(tmp_path: Path) -> None:
    """``pageerror`` is not ``console``: an exception nothing catches reaches it, and the
    console only as a side effect. Unrecorded, a page that threw during hydration produced
    diagnostics identical to a page that ran cleanly.
    """
    browser = _browser(tmp_path, at_ms=900)
    browser._on_page_error(ValueError("locale is undefined"))

    assert browser._page_errors == [
        {"atMs": 900, "name": "ValueError", "message": "locale is undefined"}
    ]


def test_a_request_is_recorded_even_when_nothing_ever_comes_back(tmp_path: Path) -> None:
    """A request still in flight when the scenario ends is in neither ``responses`` nor
    ``failedRequests`` — which is exactly the shape of a hung endpoint.
    """
    browser = _browser(tmp_path, at_ms=200)
    browser._on_request(
        SimpleNamespace(
            url="http://127.0.0.1:8099/v1/pages", method="GET", resource_type="fetch"
        )
    )

    assert browser._requests == [
        {
            "atMs": 200,
            "url": "http://127.0.0.1:8099/v1/pages",
            "method": "GET",
            "resourceType": "fetch",
        }
    ]


def test_a_response_record_carries_the_status_a_5xx_assertion_needs(tmp_path: Path) -> None:
    """``requestfailed`` never fires for a completed 500, so before the ``response``
    listener existed the diagnostics file had no status in it anywhere. A plan that wrote
    ``[.responses[]? | select(.status >= 500)] | length == 0`` was reading a key nothing
    produced, and jq answers a missing field with an empty stream rather than an error —
    so the assertion passed on every run, including the ones serving 500s.
    """
    browser = _browser(tmp_path, at_ms=4200)
    browser._on_response(
        SimpleNamespace(
            url="http://127.0.0.1:8099/api/docs",
            status=503,
            request=SimpleNamespace(method="POST"),
        )
    )

    assert browser._responses == [
        {
            "atMs": 4200,
            "url": "http://127.0.0.1:8099/api/docs",
            "status": 503,
            "method": "POST",
        }
    ]


def test_a_failed_request_record_says_why_it_failed(tmp_path: Path) -> None:
    """``requestfailed`` fires for an app cancelling its own fetch just as it does for a
    refused connection. With only the URL recorded the two are the same entry, so a plan
    that gates on ``.failedRequests | length == 0`` goes red on a benign StrictMode abort
    and the only way back to green is to stop asserting on the field.
    """
    url = "http://127.0.0.1:8099/v1/pages/p_copy_links/fr"
    browser = _browser(tmp_path, at_ms=3300)
    browser._on_failed_request(
        SimpleNamespace(url=url, method="GET", failure="net::ERR_ABORTED")
    )

    assert browser._failed_requests == [
        {"atMs": 3300, "url": url, "method": "GET", "errorText": "net::ERR_ABORTED"}
    ]

    unexplained = _browser(tmp_path)
    unexplained._on_failed_request(SimpleNamespace(url=url, method="GET", failure=None))
    assert unexplained._failed_requests[0]["errorText"] == "", (
        "a missing failure reason is the empty string, never a null a jq select would skip"
    )
