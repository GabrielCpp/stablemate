"""A role selector is registered against what the browser scan emits, not a hand-built region."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module
from ostler.vet.placement import VettedComponent, Viewport, check
from ostler.vet.regions import RegionBox, RegionList

scan = load_harness_module("ostler_qa_scan")
sync_api = pytest.importorskip("playwright.sync_api")

_VIEWPORT = Viewport(width=1280, height=800)

_PAGE = """
<main>
  <div class="tabpanel-body">
    <div role="status" aria-live="polite" aria-label="Calculating reports"
         style="margin-top:16px;padding:32px;border:1px solid #ccc;text-align:center">
      <div class="stack">
        <span aria-hidden="true" style="display:inline-block;width:40px;height:40px">o</span>
        <h5>Calculating reports</h5>
        <p>Formulas are being evaluated off the main thread.</p>
      </div>
    </div>
  </div>
</main>
"""


@pytest.fixture(scope="module")
def regions() -> Iterator[list[RegionBox]]:
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no chromium to drive: {exc}")
        page: Any = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_content(_PAGE)
        yield RegionList.validate_python(scan.merge_rects(page.evaluate(scan.SCAN_JS)))
        browser.close()


def test_a_status_is_read_off_the_element_that_owns_the_role(regions: list[RegionBox]) -> None:
    """A status whose box coincides with its wrapper and `main` merges into a `main` region, while a child inside it inherits `status` as its landmark and owns no role."""
    verdicts = check(
        [VettedComponent(node_id="s.md#loading", selector='div[role="status"]', name="Calculating reports")],
        regions,
        _VIEWPORT,
    )
    assert [(v.status, v.detail) for v in verdicts] == [("matched", [])]
