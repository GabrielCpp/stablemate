"""Own the live connection to Chrome DevTools Protocol and scan the rendered DOM."""

from __future__ import annotations

from ostler.qa.harness_host import load_harness_module
from ostler.vet.regions import ScannedElement

_WALK_JS = load_harness_module("ostler_qa_scan").SCAN_JS


def connect_and_scan(cdp_url: str) -> list[ScannedElement]:
    """Attach to an already-running Chrome via CDP, walk every frame of every page, and return every visible element's exact rect + nearest landmark role."""
    from playwright.sync_api import sync_playwright

    elements: list[ScannedElement] = []
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp_url)
        try:
            for context in browser.contexts:
                for page in context.pages:
                    for frame in page.frames:
                        for raw in frame.evaluate(_WALK_JS):
                            elements.append(ScannedElement.model_validate(raw))
        finally:
            browser.close()
    return elements
