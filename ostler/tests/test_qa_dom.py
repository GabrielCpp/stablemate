"""What `attribute` and `focused` read off a real page: markup the user never sees drawn, and where keyboard focus sits."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

dom = load_harness_module("ostler_qa_dom")
sync_api = pytest.importorskip("playwright.sync_api")

_PAGE = """
<html lang="fr">
<head>
  <link rel="alternate" hreflang="en" href="/en/guide">
  <link rel="alternate" hreflang="fr" href="/fr/guide">
</head>
<body>
  <button id="open">Open</button>
  <div id="dialog" role="dialog"><input id="name"><button id="close">Close</button></div>
</body>
</html>
"""


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
def page(browser: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setattr(dom, "DOM_WAIT_S", 0.2)
    opened = browser.new_page()
    opened.set_content(_PAGE)
    yield opened
    opened.close()


def _attribute(page: Any, selector: str, **args: object) -> Any:
    return dom.verify_attribute(dom.read_attribute(page.locator(selector), args), args)


def test_the_page_language_reads_off_the_root_element(page: Any) -> None:
    assert _attribute(page, "html", name="lang", equals="fr").passed
    assert not _attribute(page, "html", name="lang", equals="en").passed


def test_an_alternate_link_in_the_head_passes_when_any_matched_element_carries_the_value(page: Any) -> None:
    assert _attribute(page, "link[rel=alternate]", name="hreflang", equals="fr").passed
    assert _attribute(page, "link[hreflang=fr]", name="href", matches="^/fr/").passed
    assert not _attribute(page, "link[rel=alternate]", name="hreflang", equals="de").passed


def test_an_element_that_is_not_on_the_page_reads_as_absent(page: Any) -> None:
    missing = _attribute(page, "#nowhere", name="lang", equals="fr")
    assert not missing.passed
    assert missing.actual == {"present": False}


def test_focus_inside_the_dialog_passes_and_focus_outside_it_names_where_it_sits(page: Any) -> None:
    page.locator("#name").focus()
    inside = dom.verify_focused(dom.read_focused(page.locator("#dialog"), {}), {})
    assert inside.passed
    page.locator("#open").focus()
    outside = dom.verify_focused(dom.read_focused(page.locator("#dialog"), {}), {})
    assert not outside.passed
    assert outside.actual == {"focused": False, "at": "button#open"}
