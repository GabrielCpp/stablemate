"""Own the live connection to Chrome DevTools Protocol and scan the rendered DOM.

`playwright` is imported lazily, inside `connect_and_scan`, so every other `vet` module (and
every test but the live-scan smoke test) stays free of the dependency.

The walk itself lives in the QA harness (`ostler_qa_scan.SCAN_JS`) rather than here, because a
QA scenario needs the same scan from inside the project's interpreter, where ostler is not
installed. One definition, two callers: `vet` classifies a state somebody else rendered, and a
QA scenario records the state it rendered itself.
"""

from __future__ import annotations

from pydantic import BaseModel

from ostler.qa.harness_host import load_harness_module
from ostler.vet.geometry import BBox

_WALK_JS = load_harness_module("ostler_qa_scan").SCAN_JS


class ScannedElement(BaseModel):
    selector: str
    bbox: BBox
    role: str = ""
    tag: str = ""


def connect_and_scan(cdp_url: str) -> list[ScannedElement]:
    """Attach to an already-running Chrome via CDP, walk every frame of every page, and
    return every visible element's exact rect + nearest landmark role."""
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
