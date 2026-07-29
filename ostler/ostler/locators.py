"""Playwright locators derived from the book — the one-to-one mapping, and where it breaks.

A screen's ``component`` / ``interaction`` children each describe one thing a user can perceive or
operate. Playwright addresses those same things with ``getByRole(role, {name})``. When the book
carries ``role:`` and ``name:``, the translation is mechanical, and this module is that translation.

**Why derive locators instead of writing them.** A test suite that hand-writes selectors drifts from
the docs silently: the doc says the control is a button called "Save", the test clicks
``.btn-primary``, and neither notices when the other changes. Deriving the locator from the book
makes the doc the single definition — a spec that can't be located is a doc defect, surfaced here
rather than as a flaky test three months later.

**One-to-one is a two-way claim**, and only one direction is free. That every component yields a
locator follows from ``role:``/``name:`` being required. That every locator yields *one* component
does not: two components on a screen sharing a role and an accessible name produce a locator
matching both, which Playwright rejects at runtime as a strict-mode violation. That collision is
visible in the book alone, so :func:`collisions` finds it before a test ever runs.

The same ``role``/``name`` pair is the accessibility contract — this is deliberate, not a
coincidence of tooling. A control that cannot be located by role and name is a control a screen
reader cannot announce either, so a book that supports Playwright end-to-end has, by construction,
described an operable UI.
"""

from __future__ import annotations

import json

from ostler import graph as graph_mod
from ostler.model import Graph
from ostler.reach import NONE_TOKENS, _screen_of

# Roles a user operates. An interactive control with no accessible name is unusable by assistive
# tech and unaddressable by `getByRole(role, {name})` — the a11y defect and the automation defect
# are the same defect, which is why one check covers both.
INTERACTIVE_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "textbox", "searchbox", "combobox", "listbox",
    "option", "menuitem", "menuitemcheckbox", "menuitemradio", "slider", "spinbutton",
    "switch", "tab", "treeitem",
})

LOCATABLE_TYPES = ("component", "interaction")

# The ARIA roles Playwright's `getByRole` accepts. The list is finite and stable, which is what
# makes `role:` checkable at all: anything outside it is not a role the app can have computed, so a
# locator built from it matches nothing — and fails looking like the app's fault rather than the
# book's. Prose in the bullet ("`progressbar` (implicit MUI role)") is the common way this happens.
ARIA_ROLES = frozenset({
    "alert", "alertdialog", "application", "article", "banner", "blockquote", "button",
    "caption", "cell", "checkbox", "code", "columnheader", "combobox", "complementary",
    "contentinfo", "definition", "deletion", "dialog", "directory", "document", "emphasis",
    "feed", "figure", "form", "generic", "grid", "gridcell", "group", "heading", "img",
    "insertion", "link", "list", "listbox", "listitem", "log", "main", "marquee", "math",
    "menu", "menubar", "menuitem", "menuitemcheckbox", "menuitemradio", "meter", "navigation",
    "none", "note", "option", "paragraph", "presentation", "progressbar", "radio", "radiogroup",
    "region", "row", "rowgroup", "rowheader", "scrollbar", "search", "searchbox", "separator",
    "slider", "spinbutton", "status", "strong", "subscript", "superscript", "switch", "tab",
    "table", "tablist", "tabpanel", "term", "textbox", "time", "timer", "toolbar", "tooltip",
    "tree", "treegrid", "treeitem",
})


def _bullet(node: dict, key: str) -> str:
    """One bullet's value, with the markdown code fence stripped.

    Selectors and key names are conventionally written as `` `.btn-save` `` in the book. The
    backticks are presentation; carrying them into a locator produces ``locator("`.btn-save`")``,
    which matches nothing and fails in a way that looks like the app's fault.
    """
    value = node.get("bullets", {}).get(key, "")
    if isinstance(value, list):
        value = value[0] if value else ""
    text = str(value).strip()
    if len(text) > 1 and text.startswith("`") and text.endswith("`"):
        text = text[1:-1].strip()
    return text


def _stated_none(value: str) -> bool:
    """Whether the bullet states "there is none" — in any spelling the book actually uses."""
    return value.strip().lower() in NONE_TOKENS


def _escape(name: str) -> str:
    return name.replace("\\", "\\\\").replace('"', '\\"')


def locator_for(node: dict) -> dict:
    """The Playwright locator for one node, and how much to trust it.

    ``strategy`` ranks the three cases the book can produce, worst last:

    - ``role`` — ``getByRole``, resilient to markup churn and identical to what a screen reader uses.
    - ``css`` — a ``selector:`` fallback for a node with no role. It works, but it couples the suite
      to the DOM and signals a node that assistive tech cannot address either.
    - ``none`` — nothing to locate by. The node names something the book cannot point at.
    """
    role, name = _bullet(node, "role"), _bullet(node, "name")
    selector = _bullet(node, "selector")

    # An unrecognized role cannot produce a working locator, so it falls back to the selector
    # rather than emitting a `getByRole` that silently matches nothing. `invalid_roles` reports it.
    if role and not _stated_none(role) and role.lower() not in ARIA_ROLES:
        role = ""

    if role and not _stated_none(role):
        if name and not _stated_none(name):
            call = f'getByRole("{role}", {{ name: "{_escape(name)}", exact: true }})'
        else:
            call = f'getByRole("{role}")'
        return {"strategy": "role", "locator": call, "role": role,
                "name": "" if _stated_none(name) else name}
    if selector:
        return {"strategy": "css", "locator": f'locator("{_escape(selector)}")',
                "role": "", "name": ""}
    return {"strategy": "none", "locator": "", "role": "", "name": ""}


def _locatables(data: dict) -> list[tuple[str, dict]]:
    """(owner, node) for every component/interaction, wherever it is defined.

    *owner* is the screen the node lives on, or — for a shared component library that screens reach
    via ``extends:`` — its own file. Scoping this to screens alone would exempt exactly the controls
    that appear on the most screens: an app shell's navbar is defined once in a component file, and
    a wrong role there is wrong everywhere it renders.

    Owner matters only for grouping collisions. A duplicate role+name is a defect within one screen
    or within one library file; the same pair appearing on two unrelated screens is not.
    """
    by_id = {n["id"]: n for n in data["nodes"]}
    out = []
    for node in data["nodes"]:
        if node["type"] not in LOCATABLE_TYPES:
            continue
        owner = _screen_of(node["id"], by_id) or node["id"].split("#", 1)[0]
        out.append((owner, node))
    return out


def _exclusive_pairs(data: dict) -> set[frozenset[str]]:
    """Unordered node pairs declared never to be in the DOM together (``exclusive-with:``).

    Symmetric: a pair counts if *either* side declares it, so an author annotating one of two
    mutually-exclusive siblings is enough.
    """
    return {frozenset((e["from"], e["to"]))
            for e in data["edges"] if e.get("via") == "exclusive-with"}


def collisions(data: dict) -> list[dict]:
    """Nodes sharing a screen, a role, and an accessible name — where one-to-one fails.

    Only ``role``-strategy nodes can collide: a CSS selector is already a distinct string, and an
    unlocatable node has nothing to collide with. Both of those are reported by their own checks.

    Only ``component`` nodes are compared. An ``interaction``'s ``role:``/``name:`` describe the
    control it fires ``on:``, so matching that control is the point, not a collision — and two
    interactions on one component (a click and a keyboard shortcut) legitimately share a locator.
    Where an interaction really is ambiguous, its component already says so, once.

    A pair declared ``exclusive-with:`` is skipped: two controls that share a locator but can never
    render at the same time are not ambiguous at runtime. The static check cannot know that, so the
    book states it — and only a pair genuinely never co-rendering may; a real same-screen collision
    is a defect to leave standing, not to annotate away.
    """
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for screen, node in _locatables(data):
        if node["type"] != "component":
            continue
        loc = locator_for(node)
        if loc["strategy"] != "role":
            continue
        groups.setdefault((screen, loc["role"], loc["name"]), []).append(node)

    exclusive = _exclusive_pairs(data)
    out = []
    for (screen, role, name), nodes in sorted(groups.items()):
        if len(nodes) < 2:
            continue
        # A node conflicts only with siblings it is not declared exclusive-with. Report the union
        # of nodes still in at least one live conflict; a group fully partitioned by exclusivity
        # (every pair declared) is not ambiguous and drops out.
        ids = [n["id"] for n in nodes]
        conflicting: set[str] = set()
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if frozenset((a, b)) not in exclusive:
                    conflicting.update((a, b))
        if len(conflicting) < 2:
            continue
        out.append({"screen": screen, "role": role, "name": name,
                    "nodes": sorted(conflicting)})
    return out


def invalid_roles(data: dict) -> list[dict]:
    """Nodes whose ``role:`` is not an ARIA role — usually a real role with prose stapled to it."""
    out = []
    for screen, node in _locatables(data):
        role = _bullet(node, "role")
        if role and not _stated_none(role) and role.lower() not in ARIA_ROLES:
            out.append({"screen": screen, "node": node["id"], "role": role})
    return out


def _base_components(data: dict) -> set[str]:
    """Nodes another component ``extends:`` — shared bases rather than rendered controls.

    A design-system row extended by several screens has no single accessible name: each consumer
    supplies its own. ``name: none`` on such a base is accurate, and demanding a name there would
    push authors to invent one for a control that never renders under that name.
    """
    return {e["to"] for e in data["edges"] if e.get("via") == "extends"}


def unnamed_interactives(data: dict) -> list[dict]:
    """Operable controls with no accessible name — unannounceable and unaddressable alike.

    Shared bases are exempt (see :func:`_base_components`); their consumers are not, so the name is
    still required exactly once per control that actually renders.
    """
    bases = _base_components(data)
    out = []
    for screen, node in _locatables(data):
        if node["id"] in bases:
            continue
        role, name = _bullet(node, "role"), _bullet(node, "name")
        if role.lower() in INTERACTIVE_ROLES and (not name or _stated_none(name)):
            out.append({"screen": screen, "node": node["id"], "role": role})
    return out


def screen_locators(data: dict, screen: str | None = None) -> list[dict]:
    """Every locatable node, grouped by its owner (a screen, or a shared component file)."""
    by_screen: dict[str, list[dict]] = {}
    for owner, node in _locatables(data):
        if screen and owner != screen and not owner.endswith(f"/{screen}.md"):
            continue
        entry = {"node": node["id"], "type": node["type"], "title": node.get("title", "")}
        entry.update(locator_for(node))
        entry["keyboard"] = _bullet(node, "keyboard")
        by_screen.setdefault(owner, []).append(entry)
    return [{"screen": s, "locators": by_screen[s]} for s in sorted(by_screen)]


def build(graph: Graph, *, surface: str | None = None, screen: str | None = None) -> dict:
    data = graph_mod.build(graph, surface=surface)
    screens = screen_locators(data, screen)
    flat = [locator for entry in screens for locator in entry["locators"]]
    return {
        "screens": screens,
        "collisions": collisions(data),
        "unnamed": unnamed_interactives(data),
        "invalid_roles": invalid_roles(data),
        "counts": {
            "locators": len(flat),
            "by_role": sum(1 for locator in flat if locator["strategy"] == "role"),
            "by_css": sum(1 for locator in flat if locator["strategy"] == "css"),
            "unlocatable": sum(1 for locator in flat if locator["strategy"] == "none"),
        },
    }


def render(data: dict) -> str:
    lines = []
    for entry in data["screens"]:
        lines.append(entry["screen"])
        for locator in entry["locators"]:
            mark = {"role": " ", "css": "~", "none": "!"}[locator["strategy"]]
            shown = locator["locator"] or "(nothing to locate by)"
            lines.append(f"  {mark} {locator['node'].split('#')[-1]}: page.{shown}")
            if locator["keyboard"]:
                lines.append(f"      keyboard: {locator['keyboard']}")
        lines.append("")
    for collision in data["collisions"]:
        lines.append(f"! ambiguous: role={collision['role']} name={collision['name']!r} matches "
                     + ", ".join(n.split("#")[-1] for n in collision["nodes"]))
    for unnamed in data["unnamed"]:
        lines.append(f"! unnamed {unnamed['role']}: {unnamed['node']}")
    for bad in data["invalid_roles"]:
        lines.append(f"! not an ARIA role: {bad['role']!r} on {bad['node']}")
    counts = data["counts"]
    lines.append(f"\n{counts['locators']} locator(s): {counts['by_role']} by role, "
                 f"{counts['by_css']} by selector, {counts['unlocatable']} unlocatable")
    return "\n".join(lines)


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2)
