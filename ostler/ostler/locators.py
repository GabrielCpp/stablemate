"""Playwright locators derived from the book — the one-to-one mapping, and where it breaks."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ostler import graph as graph_mod
from ostler.model import Graph, UINode
from ostler.reach import NONE_TOKENS, _screen_of
from ostler.vet import placement as placement_mod

INTERACTIVE_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "textbox", "searchbox", "combobox", "listbox",
    "option", "menuitem", "menuitemcheckbox", "menuitemradio", "slider", "spinbutton",
    "switch", "tab", "treeitem",
})

LOCATABLE_TYPES = ("component", "interaction")


def locator_target(graph: Graph, value: str, origin: Path) -> str:
    """The node identity a check locator names, or ``""`` when it names no node at all."""
    if "#" not in value:
        return ""
    if value.startswith("#"):
        try:
            rel = origin.relative_to(graph.root).as_posix()
        except ValueError:
            return ""
        return f"{rel}#{value[1:]}"
    return graph.resolve_doc_ref(value, origin=origin)


def located_node(graph: Graph, value: str, origin: Path) -> UINode | None:
    """The component or interaction a check locator names, or None when it names none."""
    target = locator_target(graph, value, origin)
    node = graph.find_ui_node(target) if target else None
    return node if node is not None and node.type in LOCATABLE_TYPES else None

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
    """One bullet's value, with the markdown code fence stripped."""
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



_HOLE_RE = re.compile(r"\$?\{([^{}]*)\}")
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
_PATH_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")

DISPLAY_LEAVES = frozenset({"name", "label", "title", "text", "caption"})


def _machine(text: str) -> str:
    """The machine-read half of a bullet: the first backticked span, else the text before ` — `."""
    text = str(text).strip()
    match = re.search(r"`([^`]*)`", text)
    if match:
        return match.group(1).strip()
    return text.split(" — ", 1)[0].strip()


def _raw_bullet(node: dict, key: str) -> str:
    value = node.get("bullets", {}).get(key, "")
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value).strip()


def repeat_of(node: dict) -> str:
    """The node's own iteration variable — `one-per:`'s machine value — or ``""``."""
    text = _machine(_raw_bullet(node, "one-per"))
    if _IDENT_RE.fullmatch(text) and not _stated_none(text):
        return text
    return ""


def unique_by_of(node: dict) -> str:
    """The distinctness claim — `unique-by:`'s machine value (one dot-path) — or ``""``."""
    text = _machine(_raw_bullet(node, "unique-by"))
    if _PATH_RE.fullmatch(text) and not _stated_none(text):
        return text
    return ""


def variants_of(node: dict) -> dict | None:
    """The enumerable variant axis: ``{"path": "field.type", "values": ["text", …]}`` or None."""
    text = _machine(_raw_bullet(node, "variants"))
    if not text or _stated_none(text):
        return None
    head, sep, rest = text.partition("=")
    path = head.strip()
    values = [v.strip() for v in rest.split("|") if v.strip()]
    if not sep or not _PATH_RE.fullmatch(path) or not values:
        return None
    return {"path": path, "values": values}


def _scopes(data: dict) -> dict[str, tuple[str, ...]]:
    """Every node's in-scope iteration variables, outermost first."""
    by_id = {n["id"]: n for n in data["nodes"]}
    linked: dict[str, list[str]] = {}
    for edge in data["edges"]:
        if edge.get("via") == "parent":
            linked.setdefault(edge["from"], []).append(edge["to"])

    cache: dict[str, tuple[str, ...]] = {}

    def scope(node_id: str, walking: frozenset[str]) -> tuple[str, ...]:
        if node_id in cache:
            return cache[node_id]
        node = by_id.get(node_id)
        if node is None or node_id in walking:
            return ()
        walking |= {node_id}
        inherited: list[str] = []
        parents = ([node["parent"]] if node.get("parent") else []) + linked.get(node_id, [])
        for parent in parents:
            for var in scope(parent, walking):
                if var not in inherited:
                    inherited.append(var)
        own = repeat_of(node)
        if own and own not in inherited:
            inherited.append(own)
        cache[node_id] = tuple(inherited)
        return cache[node_id]

    for node in data["nodes"]:
        scope(node["id"], frozenset())
    return cache


def scopes(data: dict) -> dict[str, tuple[str, ...]]:
    """Public face of `_scopes` for consumers outside this module (``qa/context``)."""
    return _scopes(data)


def compile_template(name: str, scope: tuple[str, ...]) -> dict | None:
    """Segments for a templated name, or None when the name carries no hole."""
    matches = list(_HOLE_RE.finditer(name))
    if not matches:
        if "{" in name or "}" in name:
            return {"template": name, "segments": [{"kind": "literal", "text": name}],
                    "binds": [], "malformed": True}
        return None
    segments: list[dict] = []
    binds: list[str] = []
    malformed = False
    last = 0
    for match in matches:
        if match.start() > last:
            text = name[last:match.start()]
            malformed = malformed or "{" in text or "}" in text
            segments.append({"kind": "literal", "text": text})
        hole = match.group(1).strip()
        if _PATH_RE.fullmatch(hole) and hole.split(".", 1)[0] in scope:
            segments.append({"kind": "bind", "path": hole})
            binds.append(hole)
        else:
            segments.append({"kind": "opaque", "expr": hole})
        last = match.end()
    if last < len(name):
        text = name[last:]
        malformed = malformed or "{" in text or "}" in text
        segments.append({"kind": "literal", "text": text})
    return {"template": name, "segments": segments, "binds": binds, "malformed": malformed}


def _pattern(segments: list[dict]) -> str:
    """The portable-regex intersection of a template: escaped literals, `.*` for every hole."""
    return "".join(re.escape(s["text"]) if s["kind"] == "literal" else ".*" for s in segments)


def locator_for(node: dict, *, scope: tuple[str, ...] = ()) -> dict:
    """The Playwright locator for one node, and how much to trust it."""
    role, name = _bullet(node, "role"), _bullet(node, "name")
    selector = _bullet(node, "selector")

    if role and not _stated_none(role) and role.lower() not in ARIA_ROLES:
        role = ""

    if role and not _stated_none(role):
        if scope and name and not _stated_none(name):
            compiled = compile_template(name, scope)
            if compiled and not compiled["malformed"]:
                return {"strategy": "template", "locator": "", "role": role, "name": name,
                        "template": name, "iterates": scope[-1],
                        "segments": compiled["segments"], "binds": compiled["binds"]}
        if name and not _stated_none(name):
            call = f'getByRole("{role}", {{ name: "{_escape(name)}", exact: true }})'
        else:
            call = f'getByRole("{role}")'
        return {"strategy": "role", "locator": call, "role": role,
                "name": "" if _stated_none(name) else name}
    if selector:
        scheme = placement_mod.parse_scheme_selector(selector)
        if scheme is not None:
            return {"strategy": "scheme", "locator": "", "role": "", "name": "",
                    "scheme": scheme[0], "value": scheme[1]}
        return {"strategy": "css", "locator": f'locator("{_escape(selector)}")',
                "role": "", "name": ""}
    return {"strategy": "none", "locator": "", "role": "", "name": ""}


def _locatables(data: dict) -> list[tuple[str, dict]]:
    """(owner, node) for every component/interaction, wherever it is defined."""
    by_id = {n["id"]: n for n in data["nodes"]}
    out = []
    for node in data["nodes"]:
        if node["type"] not in LOCATABLE_TYPES:
            continue
        owner = _screen_of(node["id"], by_id) or node["id"].split("#", 1)[0]
        out.append((owner, node))
    return out


def _exclusive_pairs(data: dict) -> set[frozenset[str]]:
    """Unordered node pairs declared never to be in the DOM together (``exclusive-with:``)."""
    return {frozenset((e["from"], e["to"]))
            for e in data["edges"] if e.get("via") == "exclusive-with"}


IDENTITY_KEYS = ("role", "name")


def malformed_identity(node: dict) -> list[str]:
    """The identity keys this node states more than once, in registry order."""
    bullets = node.get("bullets", {})
    return [key for key in IDENTITY_KEYS if isinstance(bullets.get(key), list)]


def collisions(data: dict) -> list[dict]:
    """Nodes sharing a screen, a role, and an accessible name — where one-to-one fails."""
    scopes = _scopes(data)
    groups: dict[tuple[str, str, str], list[dict]] = {}
    templated: dict[tuple[str, str], list[tuple[dict, dict]]] = {}
    for screen, node in _locatables(data):
        if node["type"] != "component" or malformed_identity(node):
            continue
        loc = locator_for(node, scope=scopes.get(node["id"], ()))
        if loc["strategy"] == "template":
            templated.setdefault((screen, loc["role"]), []).append((node, loc))
        if loc["strategy"] != "role":
            continue
        groups.setdefault((screen, loc["role"], loc["name"]), []).append(node)

    exclusive = _exclusive_pairs(data)

    def _live(ids: list[str]) -> set[str]:
        conflicting: set[str] = set()
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if frozenset((a, b)) not in exclusive:
                    conflicting.update((a, b))
        return conflicting

    out = []
    for (screen, role, name), nodes in sorted(groups.items()):
        if len(nodes) < 2:
            continue
        conflicting = _live([n["id"] for n in nodes])
        if len(conflicting) < 2:
            continue
        out.append({"screen": screen, "role": role, "name": name,
                    "nodes": sorted(conflicting)})
    for (screen, role), pairs in sorted(templated.items()):
        for node, loc in pairs:
            pattern = _pattern(loc["segments"])
            for (other_screen, other_role, name), statics in sorted(groups.items()):
                if (other_screen, other_role) != (screen, role) or not name:
                    continue
                if not re.fullmatch(pattern, name):
                    continue
                conflicting = _live([node["id"]] + [n["id"] for n in statics])
                if len(conflicting) < 2 or node["id"] not in conflicting:
                    continue
                out.append({"screen": screen, "role": role, "name": name,
                            "template": loc["template"], "nodes": sorted(conflicting)})
    return out


def invalid_roles(data: dict) -> list[dict]:
    """Nodes whose ``role:`` is not an ARIA role — usually a real role with prose stapled to it."""
    out = []
    for screen, node in _locatables(data):
        role = _bullet(node, "role")
        if role and not _stated_none(role) and role.lower() not in ARIA_ROLES:
            out.append({"screen": screen, "node": node["id"], "role": role})
    return out


def static_templates(data: dict) -> list[dict]:
    """Repeated nodes whose name carries no per-instance datum — one name, many instances."""
    scopes = _scopes(data)
    out = []
    for screen, node in _locatables(data):
        var = repeat_of(node)
        if not var:
            continue
        name = _bullet(node, "name")
        if not name or _stated_none(name):
            continue
        compiled = compile_template(name, scopes.get(node["id"], ()))
        binds = [] if compiled is None or compiled["malformed"] else compiled["binds"]
        if any(b.split(".", 1)[0] == var for b in binds):
            continue
        out.append({"screen": screen, "node": node["id"], "template": name, "iterates": var})
    return out


def unproven_unique_names(data: dict) -> list[dict]:
    """Repeated nodes discriminated only by display values, with no ``unique-by:`` claim."""
    scopes = _scopes(data)
    out = []
    for screen, node in _locatables(data):
        var = repeat_of(node)
        if not var or unique_by_of(node):
            continue
        compiled = compile_template(_bullet(node, "name"), scopes.get(node["id"], ()))
        if compiled is None or compiled["malformed"]:
            continue
        own = [b for b in compiled["binds"] if b.split(".", 1)[0] == var]
        if own and all(b.rsplit(".", 1)[-1] in DISPLAY_LEAVES for b in own):
            out.append({"screen": screen, "node": node["id"],
                        "template": compiled["template"], "binds": own})
    return out


def malformed_templates(data: dict) -> list[dict]:
    """Repeated-scope nodes whose name template has an unbalanced brace — the one hard error."""
    scopes = _scopes(data)
    out = []
    for screen, node in _locatables(data):
        if not scopes.get(node["id"]):
            continue
        compiled = compile_template(_bullet(node, "name"), scopes[node["id"]])
        if compiled and compiled["malformed"]:
            out.append({"screen": screen, "node": node["id"], "template": compiled["template"]})
    return out


def templates_outside_repeat(data: dict) -> list[dict]:
    """Nodes whose ``name:`` reads as a template but which repeat over nothing."""
    scopes = _scopes(data)
    out = []
    for screen, node in _locatables(data):
        if scopes.get(node["id"]):
            continue
        name = _bullet(node, "name")
        if not name or _stated_none(name):
            continue
        compiled = compile_template(name, ())
        if compiled is None or compiled["malformed"]:
            continue
        out.append({"screen": screen, "node": node["id"], "template": name})
    return out


def invalid_variants(data: dict) -> list[dict]:
    """Repeated nodes whose ``variants:`` machine value the micro-syntax rejects."""
    out = []
    for screen, node in _locatables(data):
        raw = _raw_bullet(node, "variants")
        if not raw or not repeat_of(node):
            continue
        if _stated_none(_machine(raw)):
            continue
        if variants_of(node) is None:
            out.append({"screen": screen, "node": node["id"], "value": _machine(raw)})
    return out


def _base_components(data: dict) -> set[str]:
    """Nodes another component ``extends:`` — shared bases rather than rendered controls."""
    return {e["to"] for e in data["edges"] if e.get("via") == "extends"}


def unnamed_interactives(data: dict) -> list[dict]:
    """Operable controls with no accessible name — unannounceable and unaddressable alike."""
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
    scopes = _scopes(data)
    for owner, node in _locatables(data):
        if screen and owner != screen and not owner.endswith(f"/{screen}.md"):
            continue
        entry = {"node": node["id"], "type": node["type"], "title": node.get("title", "")}
        entry.update(locator_for(node, scope=scopes.get(node["id"], ())))
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
        "static_templates": static_templates(data),
        "unproven_unique": unproven_unique_names(data),
        "malformed_templates": malformed_templates(data),
        "invalid_variants": invalid_variants(data),
        "counts": {
            "locators": len(flat),
            "by_role": sum(1 for locator in flat if locator["strategy"] == "role"),
            "by_template": sum(1 for locator in flat if locator["strategy"] == "template"),
            "by_css": sum(1 for locator in flat if locator["strategy"] == "css"),
            "by_scheme": sum(1 for locator in flat if locator["strategy"] == "scheme"),
            "unlocatable": sum(1 for locator in flat if locator["strategy"] == "none"),
        },
    }


def render(data: dict) -> str:
    lines = []
    for entry in data["screens"]:
        lines.append(entry["screen"])
        for locator in entry["locators"]:
            mark = {
                "role": " ", "template": "*", "css": "~", "scheme": "@", "none": "!",
            }[locator["strategy"]]
            if locator["strategy"] == "template":
                shown = (f'getByRole("{locator["role"]}") one per {locator["iterates"]}, '
                         f'name from {locator["template"]!r}')
            elif locator["strategy"] == "scheme":
                shown = f'{locator["scheme"]}={locator["value"]} (no compiled driver yet)'
            else:
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
    for item in data.get("static_templates", []):
        lines.append(f"! static template: {item['node']} repeats one-per {item['iterates']} but "
                     f"{item['template']!r} names every instance the same")
    for item in data.get("unproven_unique", []):
        lines.append(f"~ unproven unique name: {item['node']} binds only display values "
                     f"({', '.join(item['binds'])}) and claims no unique-by")
    for item in data.get("malformed_templates", []):
        lines.append(f"! unbalanced brace in template: {item['template']!r} on {item['node']}")
    for item in data.get("invalid_variants", []):
        lines.append(f"~ unparsable variants: {item['value']!r} on {item['node']}")
    counts = data["counts"]
    lines.append(f"\n{counts['locators']} locator(s): {counts['by_role']} by role, "
                 f"{counts.get('by_template', 0)} templated, "
                 f"{counts['by_css']} by selector, {counts['by_scheme']} by scheme "
                 f"(uncompiled), {counts['unlocatable']} unlocatable")
    return "\n".join(lines)


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2)
