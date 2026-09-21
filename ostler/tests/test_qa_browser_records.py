"""The shape of what a browser scenario records about the page it drove."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_HARNESS = Path(__file__).resolve().parents[1] / "ostler/qa/harness"
sys.path.insert(0, str(_HARNESS))

_SOURCE = _HARNESS / "ostler_qa_browser.py"
_spec = importlib.util.spec_from_file_location("ostler_qa_browser_under_test", _SOURCE)
assert _spec is not None and _spec.loader is not None
ostler_qa_browser = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ostler_qa_browser)
Browser = ostler_qa_browser.Browser


def _browser(tmp_path: Path, at_ms: int = 0, secrets: Any = (), **target: object) -> Any:
    declared: dict[str, object] = {
        "browser": None,
        "permissions": None,
        "recording": None,
        "viewport": None,
    }
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
    """A Playwright ``Request`` as the handlers use it."""
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
    """A Playwright ``Response``."""
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
    """A copy journey is only provable if the context can reach the clipboard."""
    assert _browser(tmp_path).permissions() == ["clipboard-read", "clipboard-write"]
    assert _browser(tmp_path, browser="firefox").permissions() == []
    assert _browser(tmp_path, permissions=["geolocation"]).permissions() == ["geolocation"]
    assert _browser(tmp_path, permissions=[]).permissions() == [], (
        "an explicit empty list denies, it does not fall back"
    )


def test_every_console_message_is_kept_not_only_the_errors(tmp_path: Path) -> None:
    """A scenario that fails with an empty ``consoleErrors`` used to leave nothing to read, though the warning that explains it — a React hydration or key warning, levelled ``warn`` — was right there on the console and thrown away."""
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
    """``pageerror`` is not ``console``: an exception nothing catches reaches it, and the console only as a side effect."""
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
            "stack": "TypeError: locale is undefined\n    at Intl (app.js:12:4)",
        }
    ]


def test_a_request_is_recorded_even_when_nothing_ever_comes_back(tmp_path: Path) -> None:
    """A request still in flight when the scenario ends is in neither ``responses`` nor ``failedRequests`` — which is exactly the shape of a hung endpoint."""
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
    """``requestfailed`` never fires for a completed 500, so before the ``response`` listener existed the diagnostics file had no status in it anywhere."""
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
    """The gate is the runner's, because a gate the plan writes is a gate it can write four fifths of."""
    browser = _browser(tmp_path, at_ms=900)
    browser._on_page_error(
        SimpleNamespace(name="TypeError", message="locale is undefined", stack="")
    )

    problems = browser.unclean()

    assert len(problems) == 1
    assert "uncaught page error" in problems[0]
    assert "locale is undefined" in problems[0]


def test_a_5xx_fails_the_scenario_and_a_4xx_does_not(tmp_path: Path) -> None:
    """Only the two conditions no scenario ever means to provoke are automatic."""
    browser = _browser(tmp_path, at_ms=4200)
    for status in (404, 422):
        browser._on_response(
            _response(
                _request(f"http://127.0.0.1:8099/api/docs/{status}", method="POST"),
                status=status,
            )
        )
    assert browser.unclean() == []

    browser._on_response(
        _response(_request("http://127.0.0.1:8099/api/docs", method="POST"), status=503)
    )

    problems = browser.unclean()
    assert len(problems) == 1
    assert "503" in problems[0]
    assert "http://127.0.0.1:8099/api/docs" in problems[0]


def test_a_failed_request_record_says_why_it_failed(tmp_path: Path) -> None:
    """``requestfailed`` fires for an app cancelling its own fetch just as it does for a refused connection."""
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
    """The defect this exists for: a page whose content is a narrow column against the right margin, under a scenario that passes."""
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

    regions = json.loads(
        (tmp_path / "screenshots/scenario-target.regions.json").read_text(encoding="utf-8")
    )
    assert [region["role"] for region in regions] == ["banner", "article", "listitem"]
    assert regions[1]["selectors"] == ["article.prose"]
    assert regions[1]["bbox"] == {"x": 1180, "y": 88, "width": 250, "height": 3800}


def test_a_document_wider_than_its_window_is_flagged_without_a_threshold(tmp_path: Path) -> None:
    """Two pathologies need no judgement call, so they are stated in the file rather than left for the reader to derive: a document laid out wider than the viewport, and a region that begins past the right edge."""
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
    """A URL and a status is the Network *list*; the panel a person opens is the headers, the payload and the body."""
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
    """Every path through body capture writes something."""
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
    """The evidence directory is not a proxy log."""
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
    """Recording headers and bodies is recording credentials unless something stops it."""
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
    """``console.log("state", store)`` prints ``state {items: Array(3), …}``."""
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
    """The diagnostics file is written after the scenario returns its verdict, so anything only the file has is unassertable."""
    browser = _browser(tmp_path)
    for level, text in (("warning", "hydration mismatch"), ("error", "boom"), ("log", "ok")):
        browser._on_console(SimpleNamespace(type=level, text=text, location=None, args=[]))

    assert [entry["type"] for entry in browser.console()] == ["warning", "error", "log"]
    assert [entry["text"] for entry in browser.console(contains="hydration")] == [
        "hydration mismatch"
    ]
    assert [entry["text"] for entry in browser.console_errors()] == ["boom"]


def test_a_favicon_the_page_never_asked_for_is_not_the_product_failing(tmp_path: Path) -> None:
    """Chrome fetches ``/favicon.ico`` whether the markup requests it or not, so a page that ships none logs a 404 at ``error`` level on a completely clean tree."""
    browser = _browser(tmp_path)
    browser._on_console(
        SimpleNamespace(
            type="error",
            text="Failed to load resource: the server responded with a status of 404",
            location={"url": "http://localhost:8000/favicon.ico", "lineNumber": 0},
            args=[],
        )
    )
    browser._on_console(
        SimpleNamespace(
            type="error",
            text="TypeError: seats.map is not a function",
            location={"url": "http://localhost:8000/app.js", "lineNumber": 12},
            args=[],
        )
    )

    assert [entry["text"] for entry in browser.console_errors()] == [
        "TypeError: seats.map is not a function"
    ]
    assert len(browser.console(level="error")) == 2, "nothing is hidden from the record"
    assert len(browser.console_errors(ignore_urls=())) == 2, "and a plan can still ask"


def test_the_diagnostics_file_is_the_whole_record_and_names_what_it_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The post-run reader has no browser to open and no session to re-drive."""
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
    """An `EventSource`, a long poll or a hung endpoint never fires ``requestfinished``, so no body is ever fetched for it — deliberately, since fetching one there would block the event dispatcher for as long as the stream stays open."""
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


def _fake_playwright(contexts: list[dict[str, Any]]) -> Any:
    """A Playwright stand-in that records the context options `open` asks for."""

    def new_context(**options: Any) -> Any:
        contexts.append(options)
        return SimpleNamespace(
            new_page=lambda: SimpleNamespace(on=lambda *_: None),
            tracing=SimpleNamespace(start=lambda **_: None),
            new_cdp_session=lambda _page: SimpleNamespace(send=lambda *_a, **_k: None),
        )

    chromium = SimpleNamespace(
        launch=lambda **_: SimpleNamespace(new_context=new_context),
    )
    return lambda: SimpleNamespace(start=lambda: SimpleNamespace(chromium=chromium))


def _open_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    recording: dict[str, Any],
    viewport: dict[str, int] | None = None,
) -> dict[str, Any]:
    contexts: list[dict[str, Any]] = []
    monkeypatch.setattr(ostler_qa_browser, "sync_playwright", _fake_playwright(contexts))
    browser = _browser(tmp_path, recording=recording, viewport=viewport)
    browser._listen = lambda page: None
    browser.open()
    assert len(contexts) == 1
    return contexts[0]


def test_a_required_recording_is_filmed_at_the_viewport_the_target_declares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect: every plan that did not declare a small viewport lost its scenario."""
    default = _open_options(
        tmp_path, monkeypatch, recording={"required": True, "mode": "viewport"}
    )
    assert default["viewport"] == {"width": 1440, "height": 900}
    assert default["record_video_size"] == default["viewport"]

    declared = _open_options(
        tmp_path,
        monkeypatch,
        recording={"required": True, "mode": "viewport"},
        viewport={"width": 1280, "height": 1024},
    )
    assert declared["viewport"] == {"width": 1280, "height": 1024}
    assert declared["record_video_size"] == declared["viewport"]


def test_nothing_is_filmed_when_the_target_asks_for_no_viewport_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The size rides with the directory: neither is set unless Playwright is doing the filming."""
    window = _open_options(
        tmp_path, monkeypatch, recording={"required": True, "mode": "window"}
    )
    assert "record_video_dir" not in window and "record_video_size" not in window

    optional = _open_options(tmp_path, monkeypatch, recording={"required": False})
    assert "record_video_dir" not in optional and "record_video_size" not in optional


def test_the_harness_and_ostler_agree_on_the_viewport_a_plan_does_not_declare() -> None:
    """Two copies of one number, in two interpreters, with an abort between them."""
    from ostler.qa.drivers import DEFAULT_VIEWPORT

    assert ostler_qa_browser.DEFAULT_VIEWPORT == DEFAULT_VIEWPORT




def _record(browser: Any, url: str, *, status: int = 200, body: bytes = b"{}") -> None:
    """One complete exchange, through both handlers the real page drives: the status arrives on `response`, the body on `requestfinished`, and they land in the one shared record."""
    request = _request(url)
    response = _response(request, status=status, body=body)
    request.response = lambda: response
    browser._on_response(response)
    browser._on_request_finished(request)


def test_a_response_is_selected_by_route_and_read_as_status_url_and_payload(tmp_path: Path) -> None:
    """`RecordedResponse` is the adapter between a transcript and the four verifiers that read a response."""
    browser = _browser(tmp_path)
    _record(browser, "http://127.0.0.1:8099/api/widgets", status=201, body=b'{"id": 7}')
    found = browser.response_for("/api/widgets")
    assert found.status == 201
    assert found.url == "http://127.0.0.1:8099/api/widgets"
    assert found.json() == {"id": 7}
    assert found.text == '{"id": 7}'


def test_a_route_the_page_never_requested_says_what_it_did_request(tmp_path: Path) -> None:
    """The failure message is the whole value here: a book naming a route the page does not call is a defect in the book, and the routes it *did* call are what a repair needs."""
    browser = _browser(tmp_path)
    _record(browser, "http://127.0.0.1:8099/api/agents")
    with pytest.raises(LookupError) as excinfo:
        browser.response_for("/api/widgets")
    assert "/api/widgets" in str(excinfo.value)
    assert "/api/agents" in str(excinfo.value)


def test_two_responses_on_one_route_are_undetermined_rather_than_the_first(tmp_path: Path) -> None:
    """Undetermined ⇒ do not answer."""
    browser = _browser(tmp_path)
    _record(browser, "http://127.0.0.1:8099/api/widgets", status=409)
    _record(browser, "http://127.0.0.1:8099/api/widgets", status=201)
    with pytest.raises(LookupError) as excinfo:
        browser.response_for("/api/widgets")
    assert "2 responses" in str(excinfo.value)
    assert "409" in str(excinfo.value) and "201" in str(excinfo.value)


def test_a_body_the_recorder_did_not_keep_is_not_read_as_an_empty_one(tmp_path: Path) -> None:
    """`bodyOmitted` is the recorder saying it chose not to keep this payload."""
    browser = _browser(tmp_path)
    _record(browser, "http://127.0.0.1:8099/api/widgets")
    browser._responses[0]["bodyOmitted"] = "too large"
    with pytest.raises(LookupError):
        browser.response_for("/api/widgets").json()


def test_a_window_excludes_the_exchanges_that_preceded_the_action(tmp_path: Path) -> None:
    """A response recorded before the click is not an observation of the click."""
    browser = _browser(tmp_path)
    _record(browser, "http://127.0.0.1:8099/api/widgets", status=200)
    window = browser.window()
    with pytest.raises(LookupError) as excinfo:
        window.response_for("/api/widgets")
    assert "after the action" in str(excinfo.value)
    _record(browser, "http://127.0.0.1:8099/api/widgets", status=201)
    assert window.response_for("/api/widgets").status == 201
    with pytest.raises(LookupError):
        browser.response_for("/api/widgets")
