"""A screen settling in a real browser: its request answers, its busy sign goes, and the state that holds is the one a flow names."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
sync_api = pytest.importorskip("playwright.sync_api")
recorder = load_harness_module("ostler_qa_browser")

CEILING_S = 2.0

NODE = "gui/screens/results.md#loaded"

STATES = {
    "loaded": [{"role": "table", "name": "Results"}, {"role": "alert", "name": "Could not load results", "absent": True}],
    "error": [{"role": "alert", "name": "Could not load results"}],
}

BUSY = {"role": "progressbar", "name": "Loading results"}

_PAGE = """
<div role="progressbar" aria-label="Loading results">Loading</div>
<div id="out"></div>
<script>
  fetch("/api/results").then(async (response) => {
    document.querySelector("[role=progressbar]").remove();
    const out = document.getElementById("out");
    if (response.ok) {
      out.innerHTML = '<table aria-label="Results"><tr><td>row</td></tr></table>';
    } else {
      out.innerHTML = '<div role="alert">Could not load results</div>';
    }
  });
</script>
"""


class _Scenario:
    scenario_id = "settle"
    target = SimpleNamespace(name="web", driver="playwright")

    def __init__(self, page: Any, browser: Any, ceiling_s: float) -> None:
        self.browser_page = page
        self.diagnostics = browser
        self.ceiling_s = ceiling_s
        self.checks: list[tuple[str, bool, Any]] = []

    def mark(self) -> int:
        return harness.Qa.mark(self)

    def _record(self, label: str, condition: bool, actual: Any, expected: Any, covers: Any, *, extra: Any = None) -> bool:
        self.checks.append((label, condition, covers))
        return condition


@pytest.fixture(scope="module")
def chromium() -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no chromium to drive: {exc}")
        yield launched
        launched.close()


def _visit(chromium: Any, handler: Any) -> Iterator[_Scenario]:
    page = chromium.new_page()
    watcher = recorder.Browser(
        SimpleNamespace(recording=None, viewport=None),
        qa_dir=Path("."),
        scenario_id="settle",
        clock=lambda: 0,
        emit=lambda *args, **kwargs: None,
    )
    watcher._listen(page)
    page.route("http://fixture.test/results", lambda route: route.fulfill(content_type="text/html", body=_PAGE))
    page.route("http://fixture.test/api/results", handler)
    scenario = _Scenario(page, watcher, CEILING_S)
    yield scenario
    page.close()


def _settle(scenario: _Scenario) -> bool:
    since = scenario.mark()
    scenario.browser_page.goto("http://fixture.test/results")
    return harness.Qa.settle(
        scenario,
        NODE,
        since=since,
        requests=[("GET", "/api/results")],
        busy=BUSY,
        states=STATES,
        expect="loaded",
        covers=["okf:gui/screens/results.md#loaded:contract"],
    )


@pytest.fixture
def at_once(chromium: Any) -> Iterator[_Scenario]:
    yield from _visit(chromium, lambda route: route.fulfill(status=200, body="[]"))


@pytest.fixture
def after_a_second(chromium: Any) -> Iterator[_Scenario]:
    def handler(route: Any) -> None:
        time.sleep(1.0)
        route.fulfill(status=200, body="[]")

    yield from _visit(chromium, handler)


@pytest.fixture
def failing(chromium: Any) -> Iterator[_Scenario]:
    yield from _visit(chromium, lambda route: route.fulfill(status=500, body="no"))


@pytest.fixture
def silent(chromium: Any) -> Iterator[_Scenario]:
    yield from _visit(chromium, lambda route: None)


def test_a_screen_that_answers_at_once_settles_on_the_named_state(at_once: _Scenario) -> None:
    assert _settle(at_once)
    assert at_once.checks[0][2] == ["okf:gui/screens/results.md#loaded:contract"]


def test_a_screen_that_answers_within_the_ceiling_settles_on_the_named_state(after_a_second: _Scenario) -> None:
    started = time.monotonic()
    assert _settle(after_a_second)
    assert time.monotonic() - started >= 1.0


def test_a_screen_that_answers_with_an_error_fails_at_once_naming_the_state(failing: _Scenario) -> None:
    started = time.monotonic()
    assert not _settle(failing)
    assert time.monotonic() - started < CEILING_S / 2
    assert "expected state 'loaded', screen shows 'error'" in failing.checks[0][0]


def test_a_screen_whose_request_never_answers_fails_at_the_ceiling_naming_the_request(silent: _Scenario) -> None:
    started = time.monotonic()
    assert not _settle(silent)
    elapsed = time.monotonic() - started
    assert CEILING_S * 0.9 <= elapsed < CEILING_S * 2
    label = silent.checks[0][0]
    assert "GET /api/results" in label
    assert f"{CEILING_S:g}s" in label
