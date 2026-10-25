"""A rewrite rule rewrites, counts what it saw, marks the exchange, and fails the scenario when it changed nothing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

browser_module = load_harness_module("ostler_qa_browser")
harness = load_harness_module("ostler_qa")


class _Context:
    def __init__(self) -> None:
        self.routes: list[tuple[Any, Any]] = []

    def route(self, predicate: Any, handler: Any) -> None:
        self.routes.append((predicate, handler))


class _Route:
    def __init__(self, request: Any, body: str) -> None:
        self.request = request
        self._body = body
        self.fulfilled: list[tuple[Any, str]] = []
        self.fell_back = False

    def fetch(self) -> Any:
        return SimpleNamespace(text=lambda: self._body)

    def fulfill(self, *, response: Any, body: str) -> None:
        self.fulfilled.append((response, body))

    def fallback(self) -> None:
        self.fell_back = True


def _request(url: str = "http://127.0.0.1:8099/api/report/data", method: str = "POST") -> Any:
    return SimpleNamespace(
        url=url, method=method, resource_type="fetch", headers={}, post_data=None,
        failure=None, timing={"responseEnd": -1}, response=lambda: None,
    )


def _browser(tmp_path: Path) -> tuple[Any, _Context]:
    browser = browser_module.Browser(
        SimpleNamespace(browser=None, permissions=None, recording=None, viewport=None),
        qa_dir=tmp_path, scenario_id="scenario", clock=lambda: 0, emit=lambda record: None,
    )
    browser._context = _Context()
    return browser, browser._context


def _installed(tmp_path: Path, event: str = "POST /api/report/data") -> tuple[Any, Any, Any]:
    browser, context = _browser(tmp_path)
    browser.intercept("rewrite", event=event, find="1300", replace="4200")
    (predicate, handler), = context.routes
    return browser, predicate, handler


def test_the_rule_matches_the_event_path_whatever_the_query_and_not_another_path(tmp_path: Path) -> None:
    _, predicate, _ = _installed(tmp_path, "POST /api/report/{id}/data")

    assert predicate("http://127.0.0.1:8099/api/report/7/data?x=1")
    assert not predicate("http://127.0.0.1:8099/api/report/7/data/more")
    assert not predicate("http://127.0.0.1:8099/api/other")


def test_the_handler_replaces_the_text_counts_the_exchange_and_marks_its_record(tmp_path: Path) -> None:
    browser, _, handler = _installed(tmp_path)
    request = _request()
    route = _Route(request, '{"total": 1300, "again": 1300}')

    handler(route)

    assert [body for _, body in route.fulfilled] == ['{"total": 4200, "again": 4200}']
    assert browser._intercepts == [{
        "effect": "rewrite", "event": "POST /api/report/data", "find": "1300", "replace": "4200",
        "matched": 1, "rewritten": 1,
    }]
    assert browser._record(request)["intercepted"] == {"effect": "rewrite", "replacements": 2}
    assert browser.unclean() == []


def test_a_request_with_another_method_falls_through_uncounted(tmp_path: Path) -> None:
    browser, _, handler = _installed(tmp_path)
    route = _Route(_request(method="GET"), '{"total": 1300}')

    handler(route)

    assert route.fell_back
    assert route.fulfilled == []
    assert browser._intercepts[0]["matched"] == 0
    assert browser._requests == []


def test_an_exchange_without_the_find_text_is_matched_but_not_rewritten(tmp_path: Path) -> None:
    browser, _, handler = _installed(tmp_path)
    request = _request()

    handler(_Route(request, '{"total": 9}'))

    assert (browser._intercepts[0]["matched"], browser._intercepts[0]["rewritten"]) == (1, 0)
    assert browser._record(request)["intercepted"] == {"effect": "rewrite", "replacements": 0}


def test_a_rule_that_rewrote_nothing_fails_the_scenario_naming_its_counts(tmp_path: Path) -> None:
    browser, _, handler = _installed(tmp_path)
    handler(_Route(_request(), '{"total": 9}'))

    assert browser.unclean() == [
        "intercept rewrite POST /api/report/data matched 1 exchange and rewrote 0: "
        "find text '1300' was not in the body"
    ]


def test_a_rule_no_exchange_reached_fails_the_scenario_too(tmp_path: Path) -> None:
    browser, _, _ = _installed(tmp_path)

    assert browser.unclean() == [
        "intercept rewrite POST /api/report/data matched 0 exchanges and rewrote 0: "
        "no exchange reached the rule"
    ]


def test_a_rewrite_failure_reaches_the_run_as_a_failing_assertion(tmp_path: Path) -> None:
    browser, _, handler = _installed(tmp_path)
    handler(_Route(_request(), "{}"))
    recorder = harness._Recorder(fd=-1)
    emitted: list[dict] = []
    recorder.emit = emitted.append  # type: ignore[method-assign]
    qa = harness.Qa(
        scenario_id="s", target=harness.Target("web", driver="playwright"), root=tmp_path,
        spec_dir=tmp_path, qa_dir=tmp_path / "qa", covers=["ac:1"], recorder=recorder,
    )

    harness._bind_browser_unclean(qa, browser.unclean())

    assert qa.failures == 1
    assert "rewrote 0" in emitted[0]["actual"]


def test_the_diagnostics_file_lists_the_rules(tmp_path: Path) -> None:
    browser, _, _ = _installed(tmp_path)
    browser._write_diagnostics()

    written = json.loads((tmp_path / "traces" / "scenario-diagnostics.json").read_text(encoding="utf-8"))
    assert written["schema"] == "browser-diagnostics/3"
    assert written["intercepts"][0]["event"] == "POST /api/report/data"


def test_an_unknown_effect_is_refused(tmp_path: Path) -> None:
    browser, _ = _browser(tmp_path)

    with pytest.raises(ValueError, match="unknown intercept effect"):
        browser.intercept("delay", event="GET /x", find="a", replace="b")


def test_a_scenario_without_a_browser_cannot_intercept(tmp_path: Path) -> None:
    qa = harness.Qa(
        scenario_id="s", target=harness.Target("api", driver="http"), root=tmp_path,
        spec_dir=tmp_path, qa_dir=tmp_path / "qa", covers=[], recorder=harness._Recorder(fd=-1),
    )

    with pytest.raises(RuntimeError, match="only driver='playwright'"):
        qa.intercept("rewrite", event="GET /x", find="a", replace="b")
