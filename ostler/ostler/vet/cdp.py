"""Own the live connection to Chrome DevTools Protocol and scan the rendered DOM.

`playwright` is imported lazily, inside `connect_and_scan`, so every other `vet` module (and
every test but the live-scan smoke test) stays free of the dependency.
"""

from __future__ import annotations

from pydantic import BaseModel

from .geometry import BBox

# Landmark roles (explicit `role="..."` or implicit via tag) `_WALK_JS` resolves per element,
# walking up to the nearest ancestor that carries one.
_WALK_JS = """
() => {
  const LANDMARK_TAGS = {
    NAV: "navigation", ASIDE: "complementary", HEADER: "banner",
    MAIN: "main", FORM: "form", FOOTER: "contentinfo", DIALOG: "dialog",
  };

  function landmarkRole(el) {
    let node = el;
    while (node && node !== document.documentElement.parentNode) {
      const explicit = node.getAttribute && node.getAttribute("role");
      if (explicit) return explicit;
      const implicit = LANDMARK_TAGS[node.tagName];
      if (implicit) return implicit;
      node = node.parentElement;
    }
    return "";
  }

  function selectorFor(el, index) {
    if (el.id) return "#" + el.id;
    const cls = (el.className && typeof el.className === "string")
      ? "." + el.className.trim().split(/\\s+/).join(".") : "";
    return el.tagName.toLowerCase() + cls + ":nth(" + index + ")";
  }

  const out = [];
  const all = document.querySelectorAll("*");
  for (let i = 0; i < all.length; i++) {
    const el = all[i];
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    out.push({
      selector: selectorFor(el, i),
      tag: el.tagName.toLowerCase(),
      role: landmarkRole(el),
      bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    });
  }
  return out;
}
"""


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
