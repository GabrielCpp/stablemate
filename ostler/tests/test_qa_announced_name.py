"""A live region a book names by the text it announces is found by that text, since a browser computes no name from an alert's content."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

ostler_qa = load_harness_module("ostler_qa")
sync_api = pytest.importorskip("playwright.sync_api")

_PAGE = """
<div role="alert">Saved, but the export is still running.</div>
<div role="alert">Categories updated.</div>
<div role="alert" aria-label="Quota">You have 3 left.</div>
"""


@pytest.fixture(scope="module")
def page() -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no chromium to drive: {exc}")
        opened = browser.new_page()
        opened.set_content(_PAGE)
        yield opened
        browser.close()


def _by_role(page: Any, role: str, name: str) -> Any:
    return ostler_qa.Qa.by_role(SimpleNamespace(browser_page=page), role, name=name)


def test_an_alert_is_found_by_the_text_it_announces(page: Any) -> None:
    assert page.get_by_role("alert", name="Categories updated.").count() == 0

    found = _by_role(page, "alert", "Categories updated.")

    assert found.count() == 1
    assert found.inner_text() == "Categories updated."


def test_an_alert_that_announces_other_text_is_not_found(page: Any) -> None:
    assert _by_role(page, "alert", "Profile updated.").count() == 0
