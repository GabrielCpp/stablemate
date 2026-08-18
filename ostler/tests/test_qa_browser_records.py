"""The shape of what a browser scenario records about the page it drove.

These are the diagnostics a plan asserts on, so their field names are contract. They live
in the harness now — inside the scenario's own process, where the page object is — but the
failures each one was written for are unchanged, which is why the cases came across whole.

The module is loaded by path: it is stdlib-plus-playwright and deliberately not importable
as `ostler.*`, because the interpreter that runs a scenario is the project's, not ostler's.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_HARNESS = Path(__file__).resolve().parents[1] / "ostler/qa/harness"
# The harness reaches its siblings the way the subprocess does — by directory, not by package.
sys.path.insert(0, str(_HARNESS))

_SOURCE = _HARNESS / "ostler_qa_browser.py"
_spec = importlib.util.spec_from_file_location("ostler_qa_browser_under_test", _SOURCE)
assert _spec is not None and _spec.loader is not None
ostler_qa_browser = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ostler_qa_browser)
Browser = ostler_qa_browser.Browser


def _browser(tmp_path: Path, at_ms: int = 0, secrets: Any = (), **target: object) -> Any:
    declared = {"browser": None, "permissions": None, "recording": None, "viewport": None}
    declared.update(target)
    return Browser(
        SimpleNamespace(**declared),
        qa_dir=tmp_path,
        scenario_id="scenario",
        clock=lambda: at_ms,
        emit=lambda record: None,
        secrets=secrets,
    )


def _request(
    url: str = "http://127.0.0.1:8099/v1/pages",
    *,
    method: str = "GET",
    resource_type: str = "fetch",
    headers: dict[str, str] | None = None,
    post_data: str | None = None,
    failure: str | None = None,
    timing: dict[str, float] | None = None,
    response: Any = None,
) -> Any:
    """A Playwright ``Request`` as the handlers use it.

    `headers` and `post_data` are plain attributes on the real object — no protocol call —
    which is why the handlers read them and not their `all_headers()` siblings; `timing` is
    a property whose fields are `-1` for a phase that did not happen.
    """
    return SimpleNamespace(
        url=url,
        method=method,
        resource_type=resource_type,
        headers=headers if headers is not None else {},
        post_data=post_data,
        failure=failure,
        timing=timing if timing is not None else {"responseEnd": -1},
        response=lambda: response,
    )


def _response(
    request: Any,
    *,
    status: int = 200,
    status_text: str = "OK",
    headers: dict[str, str] | None = None,
    body: Any = b"",
) -> Any:
    """A Playwright ``Response``. ``body()`` raises for a redirect, exactly as the driver
    does — `Response.body: Response body is unavailable for redirect responses`."""
    declared = headers if headers is not None else {"content-type": "application/json"}

    def _body() -> bytes:
        if isinstance(body, Exception):
            raise body
        return body

    return SimpleNamespace(
        url=request.url,
        status=status,
        status_text=status_text,
        headers=declared,
        all_headers=lambda: declared,
        request=request,
        body=_body,
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
            "args": [],
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
    browser._on_page_error(
        SimpleNamespace(
            name="TypeError",
            message="locale is undefined",
            stack="TypeError: locale is undefined\n    at Intl (app.js:12:4)",
        )
    )

    assert browser._page_errors == [
        {
            "atMs": 900,
            "name": "TypeError",
            "message": "locale is undefined",
            # The frame that threw: without it the message names no file, and triage
            # begins by reproducing a run that has already been recorded once.
            "stack": "TypeError: locale is undefined\n    at Intl (app.js:12:4)",
        }
    ]


def test_a_request_is_recorded_even_when_nothing_ever_comes_back(tmp_path: Path) -> None:
    """A request still in flight when the scenario ends is in neither ``responses`` nor
    ``failedRequests`` — which is exactly the shape of a hung endpoint.
    """
    browser = _browser(tmp_path, at_ms=200)
    browser._on_request(_request())

    assert browser._requests == [
        {
            "atMs": 200,
            "url": "http://127.0.0.1:8099/v1/pages",
            "method": "GET",
            "resourceType": "fetch",
            "requestHeaders": {},
            "requestBody": None,
        }
    ]
    assert "status" not in browser._requests[0], (
        "a request with no status is one nothing came back for — the shape of a hung endpoint"
    )


def test_a_response_record_carries_the_status_a_5xx_assertion_needs(tmp_path: Path) -> None:
    """``requestfailed`` never fires for a completed 500, so before the ``response``
    listener existed the diagnostics file had no status in it anywhere. A plan that wrote
    ``[.responses[]? | select(.status >= 500)] | length == 0`` was reading a key nothing
    produced, and jq answers a missing field with an empty stream rather than an error —
    so the assertion passed on every run, including the ones serving 500s.
    """
    browser = _browser(tmp_path, at_ms=4200)
    request = _request("http://127.0.0.1:8099/api/docs", method="POST")
    browser._on_response(_response(request, status=503, status_text="Service Unavailable"))

    assert browser._responses == [
        {
            "atMs": 4200,
            "url": "http://127.0.0.1:8099/api/docs",
            "status": 503,
            "statusText": "Service Unavailable",
            "method": "POST",
            "resourceType": "fetch",
            "requestHeaders": {},
            "requestBody": None,
            "responseHeaders": {"content-type": "application/json"},
        }
    ]
    assert browser._responses[0] is browser._requests[0], (
        "one request is one record: the response view and the request view are the same dict, "
        "so a plan that finds a 5xx reads its payload off the object it already holds"
    )


def test_an_uncaught_page_error_fails_the_scenario_without_the_plan_asking(
    tmp_path: Path,
) -> None:
    """The gate is the runner's, because a gate the plan writes is a gate it can write
    four fifths of.

    The corpus has exactly that: a helper checking console errors, failed requests and 5xx
    responses that never calls ``page_errors()``, so an uncaught exception in the app rode
    out under a green verdict. Reviewing the missing fifth was a person's job once per
    plan; here it is a condition the scenario cannot decline to observe.
    """
    browser = _browser(tmp_path, at_ms=900)
    browser._on_page_error(
        SimpleNamespace(name="TypeError", message="locale is undefined", stack="")
    )

    problems = browser._unclean()

    assert len(problems) == 1
    assert "uncaught page error" in problems[0]
    assert "locale is undefined" in problems[0]


def test_a_5xx_fails_the_scenario_and_a_4xx_does_not(tmp_path: Path) -> None:
    """Only the two conditions no scenario ever means to provoke are automatic.

    A scenario proving an error branch provokes a 4xx on purpose and must stay green; a
    500 is the server failing to answer at all, which no acceptance criterion asks for. The
    same reasoning keeps console errors and cancelled requests assertable rather than
    fatal — an app legitimately logs at error level and legitimately abandons an in-flight
    request on navigation.
    """
    browser = _browser(tmp_path, at_ms=4200)
    for status in (404, 422):
        browser._on_response(
            _response(
                _request(f"http://127.0.0.1:8099/api/docs/{status}", method="POST"),
                status=status,
            )
        )
    assert browser._unclean() == []

    browser._on_response(
        _response(_request("http://127.0.0.1:8099/api/docs", method="POST"), status=503)
    )

    problems = browser._unclean()
    assert len(problems) == 1
    assert "503" in problems[0]
    assert "http://127.0.0.1:8099/api/docs" in problems[0]


def test_a_failed_request_record_says_why_it_failed(tmp_path: Path) -> None:
    """``requestfailed`` fires for an app cancelling its own fetch just as it does for a
    refused connection. With only the URL recorded the two are the same entry, so a plan
    that gates on ``.failedRequests | length == 0`` goes red on a benign StrictMode abort
    and the only way back to green is to stop asserting on the field.
    """
    url = "http://127.0.0.1:8099/v1/pages/p_copy_links/fr"
    browser = _browser(tmp_path, at_ms=3300)
    browser._on_failed_request(_request(url, failure="net::ERR_ABORTED"))

    assert browser._failed_requests == [
        {
            "atMs": 3300,
            "url": url,
            "method": "GET",
            "resourceType": "fetch",
            "requestHeaders": {},
            "requestBody": None,
            "errorText": "net::ERR_ABORTED",
            "bodyOmitted": "request did not complete",
        }
    ]

    unexplained = _browser(tmp_path)
    unexplained._on_failed_request(_request(url, failure=None))
    assert unexplained._failed_requests[0]["errorText"] == "", (
        "a missing failure reason is the empty string, never a null a jq select would skip"
    )


def _element(selector: str, role: str, x: float, y: float, w: float, h: float) -> dict:
    return {
        "selector": selector,
        "tag": "div",
        "role": role,
        "bbox": {"x": x, "y": y, "width": w, "height": h},
    }


def _page(elements: list[dict], *, viewport=(1440, 900), document=(1440, 4000)) -> Any:
    """A page that answers the two scans, told apart by which one is being asked for."""
    frame = {
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "document": {"width": document[0], "height": document[1]},
    }
    return SimpleNamespace(
        evaluate=lambda js: frame if "innerWidth" in js else elements,
        screenshot=lambda **_: None,
    )


def test_a_screenshot_is_measured_not_only_photographed(tmp_path: Path) -> None:
    """The defect this exists for: a page whose content is a narrow column against the right
    margin, under a scenario that passes.

    Every assertion a browser plan makes addresses the accessibility tree, and the article
    below is in that tree at full standing — `by_role("article")` finds it whether it is laid
    out across the page or crushed into 250px of the 1440 available. So the run's own evidence
    could not distinguish this page from a correct one, and the only record that could was a
    PNG nothing downstream reads.
    """
    browser = _browser(tmp_path)
    browser.page = _page(
        [
            _element("header.site", "banner", 0, 0, 1440, 64),
            _element("article.prose", "article", 1180, 88, 250, 3800),
            _element("li:nth(9)", "listitem", 1180, 200, 250, 24),
        ]
    )

    measured = browser.measure(tmp_path / "screenshots/scenario-target.png")

    assert measured["schema"] == "browser-layout/1"
    article = next(region for region in measured["regions"] if region["role"] == "article")
    assert article["viewportWidthShare"] == 0.174, article
    assert article["startsRightOf"] == 0.819, "the content is pinned against the right margin"
    assert [region["role"] for region in measured["regions"]] == ["banner", "article"], (
        "a layout summary listing every listitem is as unreadable as the screenshot"
    )
    assert measured["regionCount"] == 3, "the elided regions are still counted"

    written = json.loads(
        (tmp_path / "screenshots/scenario-target.layout.json").read_text(encoding="utf-8")
    )
    assert written == measured

    # The undigested census beside it is what `ostler vet --regions` replays, so it keeps the
    # regions the digest elides — a documented component is registered against this file.
    regions = json.loads(
        (tmp_path / "screenshots/scenario-target.regions.json").read_text(encoding="utf-8")
    )
    assert [region["role"] for region in regions] == ["banner", "article", "listitem"]
    assert regions[1]["selectors"] == ["article.prose"]
    assert regions[1]["bbox"] == {"x": 1180, "y": 88, "width": 250, "height": 3800}


def test_a_document_wider_than_its_window_is_flagged_without_a_threshold(tmp_path: Path) -> None:
    """Two pathologies need no judgement call, so they are stated in the file rather than left
    for the reader to derive: a document laid out wider than the viewport, and a region that
    begins past the right edge. Everything else is a share, and the threshold that makes a
    share *wrong* belongs to the audit prompt, not to the measurement."""
    browser = _browser(tmp_path)
    browser.page = _page(
        [_element("main", "main", 0, 0, 2200, 900)], viewport=(1440, 900), document=(2200, 900)
    )
    assert browser.layout()["flags"] == ["horizontal-overflow"]

    offscreen = _browser(tmp_path)
    offscreen.page = _page([_element("aside", "complementary", 1500, 0, 300, 900)])
    assert offscreen.layout()["flags"] == ["region-starts-off-screen"]

    healthy = _browser(tmp_path)
    healthy.page = _page([_element("main", "main", 0, 64, 1400, 3900)])
    assert healthy.layout()["flags"] == []


def test_the_network_record_carries_what_the_request_and_the_response_said(
    tmp_path: Path,
) -> None:
    """A URL and a status is the Network *list*; the panel a person opens is the headers,
    the payload and the body.

    Without them a run that reproduced a bug had no more to hand triage than a screenshot
    of its consequence: an assertion could see the 500 and not the error body naming the
    column, could see the POST and not the field it sent empty. Both are on the wire the
    scenario already drove, and both are gone the moment the context closes.
    """
    browser = _browser(tmp_path, at_ms=120)
    request = _request(
        "http://127.0.0.1:8099/v1/pages",
        method="POST",
        headers={"Content-Type": "application/json", "X-Trace": "abc"},
        post_data='{"title":""}',
        timing={"responseEnd": 42.5117},
    )
    response = _response(
        request,
        status=422,
        status_text="Unprocessable Entity",
        headers={"content-type": "application/json"},
        body=b'{"error":"title must not be empty"}',
    )
    request.response = lambda: response

    browser._on_request(request)
    browser._on_response(response)
    browser._on_request_finished(request)

    record = browser.responses(status_at_least=400)[0]
    assert record["requestHeaders"] == {"content-type": "application/json", "x-trace": "abc"}
    assert record["requestBody"] == '{"title":""}'
    assert record["responseBody"] == '{"error":"title must not be empty"}'
    assert record["responseBodyBytes"] == 35
    assert record["responseBodySha256"].startswith("e")
    assert record["durationMs"] == 42.512
    assert "bodyOmitted" not in record


def test_a_body_that_cannot_be_kept_says_so_rather_than_reading_as_empty(
    tmp_path: Path,
) -> None:
    """Every path through body capture writes something.

    A record with no ``responseBody`` and no reason beside it is indistinguishable from one
    whose body was empty, so ``assert "password" not in record.get("responseBody", "")``
    passes against a body nobody captured. A redirect has no body at all, and a PNG is
    fingerprinted rather than kept — neither is an empty response, and neither may be
    recorded as one.
    """
    browser = _browser(tmp_path)
    redirected = _request("http://127.0.0.1:8099/old")
    redirect = _response(
        redirected,
        status=302,
        body=Exception("Response.body: Response body is unavailable for redirect responses"),
    )
    redirected.response = lambda: redirect
    browser._on_request(redirected)
    browser._on_request_finished(redirected)

    assert "responseBody" not in browser._requests[0]
    assert "unavailable for redirect" in browser._requests[0]["bodyOmitted"]

    image = _request("http://127.0.0.1:8099/logo.png", resource_type="image")
    image.response = lambda: _response(image, headers={"content-type": "image/png"}, body=b"\x89PNG")
    browser._on_request(image)
    browser._on_request_finished(image)

    kept = browser.requests(url_contains="logo.png")[0]
    assert kept["bodyOmitted"] == "binary"
    assert kept["responseBodyBytes"] == 4, "a binary body is still sized and digested"
    assert len(kept["responseBodySha256"]) == 64


def test_a_body_past_the_cap_is_truncated_out_loud_and_the_budget_is_finite(
    tmp_path: Path,
) -> None:
    """The evidence directory is not a proxy log.

    One 40 MB bundle would make the diagnostics file unreadable and unopenable, so both a
    per-body cap and a per-scenario budget apply — and both announce themselves, because a
    silently shortened body is a body an assertion reads the wrong answer out of.
    """
    browser = _browser(tmp_path)
    huge = _request("http://127.0.0.1:8099/bundle.js")
    huge.response = lambda: _response(
        huge,
        headers={"content-type": "application/javascript"},
        body=b"x" * (ostler_qa_browser.MAX_BODY_BYTES + 10),
    )
    browser._on_request(huge)
    browser._on_request_finished(huge)

    record = browser.requests()[0]
    assert record["responseBodyTruncated"] is True
    assert len(record["responseBody"]) == ostler_qa_browser.MAX_BODY_BYTES
    assert record["responseBodyBytes"] == ostler_qa_browser.MAX_BODY_BYTES + 10, (
        "the true size is recorded whether or not the bytes were kept"
    )

    browser._body_budget = 0
    later = _request("http://127.0.0.1:8099/data.json")
    later.response = lambda: _response(later, body=b'{"ok":true}')
    browser._on_request(later)
    browser._on_request_finished(later)

    exhausted = browser.requests(url_contains="data.json")[0]
    assert exhausted["bodyOmitted"] == "scenario body budget exhausted"
    assert exhausted["responseBodyBytes"] == 11


def test_credentials_are_masked_in_the_traffic_the_run_keeps(tmp_path: Path) -> None:
    """Recording headers and bodies is recording credentials unless something stops it.

    Evidence outlives the run: it is read in review, attached to a story, archived with the
    run directory. A declared secret is redacted wherever it appears — header, payload or
    body — and the header names that carry a credential by definition are masked to a
    length whether or not the plan declared one, since the *name* is what a plan asserts on
    and the value is what must not survive.
    """
    browser = _browser(tmp_path, secrets=["hunter2"])
    request = _request(
        "http://127.0.0.1:8099/session",
        method="POST",
        headers={"Authorization": "Bearer tok-abcdef", "Cookie": "sid=7", "Accept": "*/*"},
        post_data='{"password":"hunter2"}',
    )
    request.response = lambda: _response(request, body=b'{"token":"hunter2-session"}')
    browser._on_request(request)
    browser._on_request_finished(request)

    record = browser.requests()[0]
    assert record["requestHeaders"]["authorization"] == "[REDACTED 17 chars]"
    assert record["requestHeaders"]["cookie"] == "[REDACTED 5 chars]"
    assert record["requestHeaders"]["accept"] == "*/*", "only the credential headers are masked"
    assert record["requestBody"] == '{"password":"[REDACTED]"}'
    assert record["responseBody"] == '{"token":"[REDACTED]-session"}'


def test_a_console_message_keeps_its_arguments_not_the_consoles_rendering_of_them(
    tmp_path: Path,
) -> None:
    """``console.log("state", store)`` prints ``state {items: Array(3), …}``.

    The ellipsis is where the assertion needed the third item. The handles are live only
    while the message is being dispatched, so this is the one moment the values can be
    taken; a handle that will not serialize — a DOM node, a cycle — says so rather than
    losing the message it belonged to.
    """
    browser = _browser(tmp_path, at_ms=40, secrets=["hunter2"])
    browser._on_console(
        SimpleNamespace(
            type="log",
            text="state {items: Array(2), …}",
            location=None,
            args=[
                SimpleNamespace(json_value=lambda: "state"),
                SimpleNamespace(json_value=lambda: {"items": [1, 2], "token": "hunter2"}),
                SimpleNamespace(
                    json_value=lambda: (_ for _ in ()).throw(ValueError("cyclic"))
                ),
            ],
        )
    )

    assert browser.console(level="log")[0]["args"] == [
        "state",
        {"items": [1, 2], "token": "[REDACTED]"},
        {"unserializable": "ValueError"},
    ]


def test_the_whole_console_is_readable_mid_scenario_not_only_after_it(tmp_path: Path) -> None:
    """The diagnostics file is written after the scenario returns its verdict, so anything
    only the file has is unassertable. ``console()`` is the same records, live — the whole
    console, because the message that explains a failure is routinely a ``warn`` the error
    filter drops."""
    browser = _browser(tmp_path)
    for level, text in (("warning", "hydration mismatch"), ("error", "boom"), ("log", "ok")):
        browser._on_console(SimpleNamespace(type=level, text=text, location=None, args=[]))

    assert [entry["type"] for entry in browser.console()] == ["warning", "error", "log"]
    assert [entry["text"] for entry in browser.console(contains="hydration")] == [
        "hydration mismatch"
    ]
    assert [entry["text"] for entry in browser.console_errors()] == ["boom"]


def test_the_diagnostics_file_is_the_whole_record_and_names_what_it_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The post-run reader has no browser to open and no session to re-drive.

    The previous file kept 500 of each list silently, which cut a busy SPA off partway
    through its own startup — and left a reader unable to tell a page that made 500 requests
    from one that made 12,000. The cap is now set where no real run reaches it, and when it
    does bite it is stated in the file rather than implied by a count.
    """
    browser = _browser(tmp_path, at_ms=10)
    browser._context = SimpleNamespace(tracing=SimpleNamespace(stop=lambda **_: None))
    request = _request("http://127.0.0.1:8099/v1/pages", post_data='{"a":1}')
    request.response = lambda: _response(request, body=b'{"ok":true}')
    browser._on_request(request)
    browser._on_response(request.response())
    browser._on_request_finished(request)
    browser._on_console(SimpleNamespace(type="log", text="ready", location=None, args=[]))

    browser._write_diagnostics()

    written = json.loads(
        (tmp_path / "traces/scenario-diagnostics.json").read_text(encoding="utf-8")
    )
    assert written["schema"] == "browser-diagnostics/2"
    assert written["requests"][0]["requestBody"] == '{"a":1}'
    assert written["responses"][0]["responseBody"] == '{"ok":true}'
    assert written["consoleCount"] == 1 and written["requestCount"] == 1
    assert "truncated" not in written, "nothing was dropped, so nothing is claimed to be"
    assert written["bodyBudgetRemainingBytes"] == (
        ostler_qa_browser.MAX_BODY_BUDGET_BYTES - 11
    )

    monkeypatch.setattr(ostler_qa_browser, "DIAGNOSTICS_LIMIT", 1)
    crowded = _browser(tmp_path)
    for index in range(3):
        crowded._on_console(
            SimpleNamespace(type="log", text=f"line {index}", location=None, args=[])
        )
    crowded._write_diagnostics()
    loud = json.loads(
        (tmp_path / "traces/scenario-diagnostics.json").read_text(encoding="utf-8")
    )

    assert loud["truncated"] == {"console": {"kept": 1, "of": 3}}
    assert loud["consoleCount"] == 3


def test_a_request_that_never_completed_is_recorded_as_such_not_as_an_empty_body(
    tmp_path: Path,
) -> None:
    """An `EventSource`, a long poll or a hung endpoint never fires ``requestfinished``, so
    no body is ever fetched for it — deliberately, since fetching one there would block the
    event dispatcher for as long as the stream stays open. What must not happen is the
    resulting record reading like a 200 with an empty body.
    """
    browser = _browser(tmp_path)
    stream = _request("http://127.0.0.1:8099/stream", resource_type="eventsource")
    browser._on_request(stream)
    browser._on_response(_response(stream, headers={"content-type": "text/event-stream"}))
    browser._on_failed_request(_request("http://127.0.0.1:8099/stream", failure="net::ERR_ABORTED"))

    hung = _request("http://127.0.0.1:8099/slow")
    browser._on_request(hung)
    browser._context = SimpleNamespace(tracing=SimpleNamespace(stop=lambda **_: None))
    browser._write_diagnostics()

    written = json.loads(
        (tmp_path / "traces/scenario-diagnostics.json").read_text(encoding="utf-8")
    )
    reasons = {record["url"]: record["bodyOmitted"] for record in written["requests"]}
    assert reasons["http://127.0.0.1:8099/stream"] == "request did not complete"
    assert reasons["http://127.0.0.1:8099/slow"] == "still in flight when the scenario ended"
