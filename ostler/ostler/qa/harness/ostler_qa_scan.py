"""The DOM scan `ostler vet` is built on, in the one place both sides can reach it."""

from __future__ import annotations

from typing import Any

NAME_FROM_CONTENT = frozenset(
    {
        "button", "cell", "checkbox", "columnheader", "gridcell", "heading", "link",
        "menuitem", "menuitemcheckbox", "menuitemradio", "option", "radio", "row",
        "rowheader", "switch", "tab", "tooltip", "treeitem",
    }
)

SCAN_JS = """
() => {
  const IMPLICIT_TAGS = {
    NAV: "navigation", ASIDE: "complementary", HEADER: "banner",
    MAIN: "main", FORM: "form", FOOTER: "contentinfo", DIALOG: "dialog",
    ARTICLE: "article",
    BUTTON: "button", SUMMARY: "button", TEXTAREA: "textbox", OPTION: "option",
    IMG: "img", UL: "list", OL: "list", LI: "listitem",
    H1: "heading", H2: "heading", H3: "heading", H4: "heading",
    H5: "heading", H6: "heading",
    TABLE: "table", TR: "row", TH: "columnheader", TD: "cell",
    PROGRESS: "progressbar", HR: "separator", FIELDSET: "group", DETAILS: "group",
  };
  const INPUT_TYPES = {
    checkbox: "checkbox", radio: "radio", range: "slider", number: "spinbutton",
    search: "searchbox", button: "button", submit: "button", reset: "button",
    image: "button", hidden: "",
  };

  function ownRole(el) {
    const explicit = el.getAttribute && el.getAttribute("role");
    if (explicit) return explicit;
    if (el.tagName === "A") return el.hasAttribute("href") ? "link" : "";
    if (el.tagName === "SELECT") {
      return (el.multiple || el.size > 1) ? "listbox" : "combobox";
    }
    if (el.tagName === "INPUT") {
      const t = (el.getAttribute("type") || "text").toLowerCase();
      return t in INPUT_TYPES ? INPUT_TYPES[t] : "textbox";
    }
    return IMPLICIT_TAGS[el.tagName] || "";
  }

  function landmarkRole(el) {
    let node = el;
    while (node && node !== document.documentElement.parentNode) {
      if (node.getAttribute) {
        const role = ownRole(node);
        if (role) return role;
      }
      node = node.parentElement;
    }
    return "";
  }

  // The accessible name, computed the way the accessibility tree computes it, with the two
  // branches that actually decide a claim: an author label always wins, and only a
  // name-from-content role falls back to its own text. Nothing here guesses — a role outside
  // that set with no author label has no name, and this reports the empty string it has.
  const NAME_FROM_CONTENT = new Set([
    "button", "cell", "checkbox", "columnheader", "gridcell", "heading", "link",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option", "radio", "row",
    "rowheader", "switch", "tab", "tooltip", "treeitem",
  ]);

  function flat(text) {
    return (text || "").replace(/\\s+/g, " ").trim();
  }

  function labelledBy(el) {
    const ids = flat(el.getAttribute("aria-labelledby"));
    if (!ids) return "";
    const parts = [];
    for (const id of ids.split(" ")) {
      const target = document.getElementById(id);
      if (target) parts.push(flat(target.textContent));
    }
    return flat(parts.join(" "));
  }

  function controlLabel(el) {
    if (el.id) {
      for (const label of document.querySelectorAll("label[for]")) {
        if (label.getAttribute("for") === el.id) return flat(label.textContent);
      }
    }
    const wrapping = el.closest ? el.closest("label") : null;
    return wrapping ? flat(wrapping.textContent) : "";
  }

  function accessibleName(el, role) {
    const authored = flat(el.getAttribute("aria-label"));
    if (authored) return authored;
    const byIds = labelledBy(el);
    if (byIds) return byIds;
    if (el.tagName === "TABLE") {
      const caption = el.querySelector(":scope > caption");
      if (caption) return flat(caption.textContent);
    }
    if (el.tagName === "FIELDSET") {
      const legend = el.querySelector(":scope > legend");
      if (legend) return flat(legend.textContent);
    }
    if (el.tagName === "IMG") return flat(el.getAttribute("alt"));
    if (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA") {
      const label = controlLabel(el);
      if (label) return label;
      return flat(el.getAttribute("placeholder"));
    }
    if (NAME_FROM_CONTENT.has(role)) return flat(el.textContent);
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
    const own = ownRole(el);
    out.push({
      selector: selectorFor(el, i),
      tag: el.tagName.toLowerCase(),
      role: landmarkRole(el),
      ownRole: own,
      name: accessibleName(el, own),
      bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    });
  }
  return out;
}
"""

FRAME_JS = """
() => ({
  viewport: {width: window.innerWidth, height: window.innerHeight},
  document: {
    width: document.documentElement.scrollWidth,
    height: document.documentElement.scrollHeight,
  },
})
"""

STRUCTURAL_ROLES = frozenset(
    {
        "main",
        "navigation",
        "banner",
        "complementary",
        "contentinfo",
        "region",
        "form",
        "dialog",
        "search",
        "article",
        "table",
        "list",
        "heading",
    }
)


def merge_rects(
    elements: list[dict[str, Any]], *, rect_epsilon: float = 1.0
) -> list[dict[str, Any]]:
    """Group elements sharing a (near-)identical rect into one region."""
    groups: dict[tuple[float, float, float, float], list[dict[str, Any]]] = {}
    order: list[tuple[float, float, float, float]] = []
    for element in elements:
        box = element["bbox"]
        key = (
            round(box["x"] / rect_epsilon),
            round(box["y"] / rect_epsilon),
            round(box["width"] / rect_epsilon),
            round(box["height"] / rect_epsilon),
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(element)

    regions: list[dict[str, Any]] = []
    for key in order:
        members = groups[key]
        regions.append(
            {
                "bbox": members[0]["bbox"],
                "role": next((m["role"] for m in members if m["role"]), None),
                "selectors": [m["selector"] for m in members],
                "own_roles": [m.get("ownRole", "") for m in members],
                "names": [m.get("name", "") for m in members],
            }
        )
    return regions


def share(value: float, total: float) -> float:
    """A length as a fraction of the viewport, rounded once, here."""
    return round(value / total, 3) if total else 0.0


def summarize(frame: dict[str, Any], regions: list[dict[str, Any]]) -> dict[str, Any]:
    """The layout of one rendered state, small enough for a reader to hold at once."""
    viewport = frame["viewport"]
    document = frame["document"]
    width, height = float(viewport["width"]), float(viewport["height"])

    summary: list[dict[str, Any]] = []
    for region in regions:
        if region["role"] not in STRUCTURAL_ROLES:
            continue
        box = region["bbox"]
        summary.append(
            {
                "role": region["role"],
                "selector": region["selectors"][0],
                "bbox": {key: round(float(box[key]), 1) for key in ("x", "y", "width", "height")},
                "viewportWidthShare": share(float(box["width"]), width),
                "viewportHeightShare": share(float(box["height"]), height),
                "startsRightOf": share(float(box["x"]), width),
            }
        )

    flags: list[str] = []
    if float(document["width"]) > width + 1:
        flags.append("horizontal-overflow")
    if any(float(region["bbox"]["x"]) >= width for region in summary):
        flags.append("region-starts-off-screen")

    return {
        "viewport": {"width": width, "height": height},
        "document": {"width": float(document["width"]), "height": float(document["height"])},
        "regionCount": len(regions),
        "regions": summary,
        "flags": flags,
    }
