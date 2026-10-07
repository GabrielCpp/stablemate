"""What a page shows after a scenario takes a step on the browser itself: going back, or printing."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
sync_api = pytest.importorskip("playwright.sync_api")

_PAGE = """
<style>
  #print-only { display: none; }
  @media print { #print-only { display: block; } #screen-only { display: none; } }
</style>
<div id="screen-only">on screen</div>
<div id="print-only">on paper</div>
"""


@dataclass(frozen=True)
class _Qa:
    browser_page: Any


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no chromium to drive: {exc}")
        yield launched
        launched.close()


@pytest.fixture
def page(browser: Any) -> Iterator[Any]:
    opened = browser.new_page()
    opened.goto(f"data:text/html,{quote(_PAGE)}")
    yield opened
    opened.close()


def test_going_back_returns_the_page_to_the_address_it_came_from(page: Any) -> None:
    first = page.url
    page.goto("data:text/html,second")
    assert page.url != first
    harness.Qa.back(_Qa(page))
    assert page.url == first


def test_printing_lays_the_page_out_as_paper_shows_it(page: Any) -> None:
    harness.Qa.print_page(_Qa(page))
    assert page.locator("#print-only").is_visible()
    assert not page.locator("#screen-only").is_visible()
