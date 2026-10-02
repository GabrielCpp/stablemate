"""Playwright locators derived from the book — the one-to-one mapping, and where it breaks."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ostler import graph as graph_mod
from ostler.locator_findings import (
    InvalidRole,
    InvalidVariants,
    LocatorCollision,
    MalformedTemplate,
    StaticTemplate,
    TemplateOutsideRepeat,
    UnnamedInteractive,
    UnprovenUniqueName,
)
from ostler.model import Graph, UINode
from ostler.qa.obligation_frame import BookNode, RepeatContract, RepeatTemplate, Segment, Variants, book_nodes
from ostler.reach import NONE_TOKENS
from ostler.untyped import JsonValue
from ostler import selector_forms

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


def _bullet(node: BookNode, key: str) -> str:
    """One bullet's value, with the markdown code fence stripped."""
    text = _raw_bullet(node, key)
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


def _raw_bullet(node: BookNode, key: str) -> str:
    values = node.bullets.get(key, ())
    return values[0].strip() if values else ""


def repeat_of(node: BookNode) -> str:
    """The node's own iteration variable — `one-per:`'s machine value — or ``""``."""
    text = _machine(_raw_bullet(node, "one-per"))
    if _IDENT_RE.fullmatch(text) and not _stated_none(text):
        return text
    return ""


def unique_by_of(node: BookNode) -> str:
    """The distinctness claim — `unique-by:`'s machine value (one dot-path) — or ``""``."""
    text = _machine(_raw_bullet(node, "unique-by"))
    if _PATH_RE.fullmatch(text) and not _stated_none(text):
        return text
    return ""


def variants_of(node: BookNode) -> Variants | None:
    """The enumerable variant axis, such as ``field.type`` over ``text | number``, or None."""
    text = _machine(_raw_bullet(node, "variants"))
    if not text or _stated_none(text):
        return None
    head, sep, rest = text.partition("=")
    path = head.strip()
    values = [v.strip() for v in rest.split("|") if v.strip()]
    if not sep or not _PATH_RE.fullmatch(path) or not values:
        return None
    return Variants(path=path, values=tuple(values))


def _scopes(nodes: Mapping[str, BookNode], parents: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    """Every node's in-scope iteration variables, outermost first."""
    cache: dict[str, tuple[str, ...]] = {}

    def scope(node_id: str, walking: frozenset[str]) -> tuple[str, ...]:
        if node_id in cache:
            return cache[node_id]
        node = nodes.get(node_id)
        if node is None or node_id in walking:
            return ()
        walking |= {node_id}
        inherited: list[str] = []
        for parent in parents.get(node_id, ()):
            for var in scope(parent, walking):
                if var not in inherited:
                    inherited.append(var)
        own = repeat_of(node)
        if own and own not in inherited:
            inherited.append(own)
        cache[node_id] = tuple(inherited)
        return cache[node_id]

    for node_id in nodes:
        scope(node_id, frozenset())
    return cache


@dataclass(frozen=True, slots=True)
class LocatorBook:
    """A built graph parsed once for the locator checks: every locatable node with its owner, each node's iteration scope, and the edges the checks read."""

    locatables: tuple[tuple[str, BookNode], ...]
    scopes: Mapping[str, tuple[str, ...]]
    exclusive: frozenset[frozenset[str]]
    bases: frozenset[str]

    @classmethod
    def parse(cls, data: dict, nodes: Mapping[str, BookNode] | None = None) -> LocatorBook:
        """The book *data* serializes; *nodes* are its nodes already parsed, when the caller holds them."""
        raw_nodes = {node["id"]: node for node in data["nodes"]}
        if nodes is None:
            nodes = book_nodes(raw_nodes)
        parents: dict[str, list[str]] = {}
        for node_id, node in raw_nodes.items():
            if node.get("parent"):
                parents.setdefault(node_id, []).append(node["parent"])
        for edge in data["edges"]:
            if edge.get("via") == "parent":
                parents.setdefault(edge["from"], []).append(edge["to"])
        return cls(
            locatables=tuple(
                (node.id.split("#", 1)[0], node) for node in nodes.values() if node.type in LOCATABLE_TYPES
            ),
            scopes=_scopes(nodes, {node_id: tuple(ids) for node_id, ids in parents.items()}),
            exclusive=frozenset(
                frozenset((edge["from"], edge["to"])) for edge in data["edges"] if edge.get("via") == "exclusive-with"
            ),
            bases=frozenset(edge["to"] for edge in data["edges"] if edge.get("via") == "extends"),
        )


@dataclass(frozen=True, slots=True)
class CompiledName:
    """A templated name split into segments, the scope paths it binds, and whether a brace is unbalanced."""

    template: str
    segments: tuple[Segment, ...]
    binds: tuple[str, ...]
    malformed: bool


def compile_template(name: str, scope: tuple[str, ...]) -> CompiledName | None:
    """Segments for a templated name, or None when the name carries no hole."""
    matches = list(_HOLE_RE.finditer(name))
    if not matches:
        if "{" in name or "}" in name:
            return CompiledName(name, (Segment("literal", name),), (), malformed=True)
        return None
    segments: list[Segment] = []
    binds: list[str] = []
    malformed = False
    last = 0
    for match in matches:
        if match.start() > last:
            text = name[last:match.start()]
            malformed = malformed or "{" in text or "}" in text
            segments.append(Segment("literal", text))
        hole = match.group(1).strip()
        if _PATH_RE.fullmatch(hole) and hole.split(".", 1)[0] in scope:
            segments.append(Segment("bind", hole))
            binds.append(hole)
        else:
            segments.append(Segment("opaque", hole))
        last = match.end()
    if last < len(name):
        text = name[last:]
        malformed = malformed or "{" in text or "}" in text
        segments.append(Segment("literal", text))
    return CompiledName(name, tuple(segments), tuple(binds), malformed)


def _pattern(segments: tuple[Segment, ...]) -> str:
    """The portable-regex intersection of a template: escaped literals, `.*` for every hole."""
    return "".join(re.escape(s.value) if s.kind == "literal" else ".*" for s in segments)


@dataclass(frozen=True, slots=True)
class Locator:
    """How Playwright finds one node: by role, by a name template over a repeat scope, by selector, by scheme, or not at all."""

    strategy: str
    playwright_call: str = ""
    role: str = ""
    name: str = ""
    template: RepeatTemplate | None = None
    binds: tuple[str, ...] = ()
    scheme: str = ""
    value: str = ""

    def row(self) -> dict[str, JsonValue]:
        """The locator as `ostler locators` prints it."""
        fields: dict[str, JsonValue] = {"strategy": self.strategy, "locator": self.playwright_call,
                                        "role": self.role, "name": self.name}
        if self.template is not None:
            fields["template"] = self.template.template
            fields["iterates"] = self.template.iterates
            fields["segments"] = [segment.row() for segment in self.template.segments]
            fields["binds"] = list(self.binds)
        if self.strategy == "scheme":
            fields["scheme"] = self.scheme
            fields["value"] = self.value
        return fields


def locator_for(node: BookNode, *, scope: tuple[str, ...] = ()) -> Locator:
    """The Playwright locator for one node, and how much to trust it."""
    role, name = _bullet(node, "role"), _bullet(node, "name")
    selector = _bullet(node, "selector")

    if role and not _stated_none(role) and role.lower() not in ARIA_ROLES:
        role = ""

    if role and not _stated_none(role):
        if scope and name and not _stated_none(name):
            compiled = compile_template(name, scope)
            if compiled and not compiled.malformed:
                return Locator("template", role=role, name=name,
                               template=RepeatTemplate(name, scope[-1], compiled.segments),
                               binds=compiled.binds)
        if name and not _stated_none(name):
            call = f'getByRole("{role}", {{ name: "{_escape(name)}", exact: true }})'
        else:
            call = f'getByRole("{role}")'
        return Locator("role", playwright_call=call, role=role, name="" if _stated_none(name) else name)
    if selector:
        scheme = selector_forms.parse_scheme_selector(selector)
        if scheme is not None:
            return Locator("scheme", scheme=scheme[0], value=scheme[1])
        return Locator("css", playwright_call=f'locator("{_escape(selector)}")')
    return Locator("none")


def repeat_contract(node: BookNode, scope: tuple[str, ...]) -> RepeatContract | None:
    """The compiled repeat contract for a node in a `one-per:` scope, or None."""
    own = repeat_of(node)
    scope = scope or ((own,) if own else ())
    if not scope:
        return None
    located = locator_for(node, scope=scope)
    return RepeatContract(
        one_per=scope[-1],
        binds=located.binds,
        template=located.template,
        unique_by=unique_by_of(node),
        variants=variants_of(node),
    )


IDENTITY_KEYS = ("role", "name")


def malformed_identity(bullets: Mapping[str, object]) -> list[str]:
    """The identity keys a node's bullets state more than once, in registry order."""
    return [key for key in IDENTITY_KEYS
            if isinstance(value := bullets.get(key), list | tuple) and len(value) > 1]


def collisions(book: LocatorBook) -> list[LocatorCollision]:
    """Nodes sharing a screen, a role, and an accessible name — where one-to-one fails."""
    scopes = book.scopes
    groups: dict[tuple[str, str, str], list[BookNode]] = {}
    templated: dict[tuple[str, str], list[tuple[BookNode, RepeatTemplate]]] = {}
    for screen, node in book.locatables:
        if node.type != "component" or malformed_identity(node.bullets):
            continue
        loc = locator_for(node, scope=scopes.get(node.id, ()))
        if loc.template is not None:
            templated.setdefault((screen, loc.role), []).append((node, loc.template))
        if loc.strategy != "role":
            continue
        groups.setdefault((screen, loc.role, loc.name), []).append(node)

    exclusive = book.exclusive

    def _live(ids: list[str]) -> set[str]:
        conflicting: set[str] = set()
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if frozenset((a, b)) not in exclusive:
                    conflicting.update((a, b))
        return conflicting

    out: list[LocatorCollision] = []
    for (screen, role, name), nodes in sorted(groups.items()):
        if len(nodes) < 2:
            continue
        conflicting = _live([n.id for n in nodes])
        if len(conflicting) < 2:
            continue
        out.append(LocatorCollision(screen, role, name, tuple(sorted(conflicting))))
    for (screen, role), pairs in sorted(templated.items()):
        for node, template in pairs:
            pattern = _pattern(template.segments)
            for (other_screen, other_role, name), statics in sorted(groups.items()):
                if (other_screen, other_role) != (screen, role) or not name:
                    continue
                if not re.fullmatch(pattern, name):
                    continue
                conflicting = _live([node.id] + [n.id for n in statics])
                if len(conflicting) < 2 or node.id not in conflicting:
                    continue
                out.append(LocatorCollision(screen, role, name, tuple(sorted(conflicting)),
                                            template.template))
    return out


def invalid_roles(book: LocatorBook) -> list[InvalidRole]:
    """Nodes whose ``role:`` is not an ARIA role — usually a real role with prose stapled to it."""
    out = []
    for screen, node in book.locatables:
        role = _bullet(node, "role")
        if role and not _stated_none(role) and role.lower() not in ARIA_ROLES:
            out.append(InvalidRole(screen, node.id, role))
    return out


def static_templates(book: LocatorBook) -> list[StaticTemplate]:
    """Repeated nodes whose name carries no per-instance datum — one name, many instances."""
    scopes = book.scopes
    out = []
    for screen, node in book.locatables:
        var = repeat_of(node)
        if not var:
            continue
        name = _bullet(node, "name")
        if not name or _stated_none(name):
            continue
        compiled = compile_template(name, scopes.get(node.id, ()))
        binds = () if compiled is None or compiled.malformed else compiled.binds
        if any(b.split(".", 1)[0] == var for b in binds):
            continue
        out.append(StaticTemplate(screen, node.id, name, var))
    return out


def unproven_unique_names(book: LocatorBook) -> list[UnprovenUniqueName]:
    """Repeated nodes discriminated only by display values, with no ``unique-by:`` claim."""
    scopes = book.scopes
    out = []
    for screen, node in book.locatables:
        var = repeat_of(node)
        if not var or unique_by_of(node):
            continue
        compiled = compile_template(_bullet(node, "name"), scopes.get(node.id, ()))
        if compiled is None or compiled.malformed:
            continue
        own = [b for b in compiled.binds if b.split(".", 1)[0] == var]
        if own and all(b.rsplit(".", 1)[-1] in DISPLAY_LEAVES for b in own):
            out.append(UnprovenUniqueName(screen, node.id, compiled.template, tuple(own)))
    return out


def malformed_templates(book: LocatorBook) -> list[MalformedTemplate]:
    """Repeated-scope nodes whose name template has an unbalanced brace — the one hard error."""
    scopes = book.scopes
    out = []
    for screen, node in book.locatables:
        if not scopes.get(node.id):
            continue
        compiled = compile_template(_bullet(node, "name"), scopes[node.id])
        if compiled and compiled.malformed:
            out.append(MalformedTemplate(screen, node.id, compiled.template))
    return out


def templates_outside_repeat(book: LocatorBook) -> list[TemplateOutsideRepeat]:
    """Nodes whose ``name:`` reads as a template but which repeat over nothing."""
    scopes = book.scopes
    out = []
    for screen, node in book.locatables:
        if scopes.get(node.id):
            continue
        name = _bullet(node, "name")
        if not name or _stated_none(name):
            continue
        compiled = compile_template(name, ())
        if compiled is None or compiled.malformed:
            continue
        out.append(TemplateOutsideRepeat(screen, node.id, name))
    return out


def invalid_variants(book: LocatorBook) -> list[InvalidVariants]:
    """Repeated nodes whose ``variants:`` machine value the micro-syntax rejects."""
    out = []
    for screen, node in book.locatables:
        raw = _raw_bullet(node, "variants")
        if not raw or not repeat_of(node):
            continue
        if _stated_none(_machine(raw)):
            continue
        if variants_of(node) is None:
            out.append(InvalidVariants(screen, node.id, _machine(raw)))
    return out


def unnamed_interactives(book: LocatorBook) -> list[UnnamedInteractive]:
    """Operable controls with no accessible name — unannounceable and unaddressable alike."""
    bases = book.bases
    out = []
    for screen, node in book.locatables:
        if node.id in bases:
            continue
        role, name = _bullet(node, "role"), _bullet(node, "name")
        if role.lower() in INTERACTIVE_ROLES and (not name or _stated_none(name)):
            out.append(UnnamedInteractive(screen, node.id, role))
    return out


@dataclass(frozen=True, slots=True)
class PlacedLocator:
    """One locatable node and how Playwright finds it, with the keys its page states for it."""

    node: str
    type: str
    title: str
    locator: Locator
    keyboard: str

    def row(self) -> dict[str, JsonValue]:
        """The node's locator as `ostler locators` prints it."""
        return {"node": self.node, "type": self.type, "title": self.title, **self.locator.row(),
                "keyboard": self.keyboard}


@dataclass(frozen=True, slots=True)
class ScreenLocators:
    """The locatable nodes one owner holds, which is a screen or a shared component file."""

    screen: str
    locators: tuple[PlacedLocator, ...]

    def row(self) -> dict[str, JsonValue]:
        """The owner's locators as `ostler locators` prints them."""
        return {"screen": self.screen, "locators": [placed.row() for placed in self.locators]}


def screen_locators(book: LocatorBook, screen: str | None = None) -> list[ScreenLocators]:
    """Every locatable node, grouped by its owner (a screen, or a shared component file)."""
    by_screen: dict[str, list[PlacedLocator]] = {}
    scopes = book.scopes
    for owner, node in book.locatables:
        if screen and owner != screen and not owner.endswith(f"/{screen}.md"):
            continue
        placed = PlacedLocator(node.id, node.type, node.title, locator_for(node, scope=scopes.get(node.id, ())),
                               _bullet(node, "keyboard"))
        by_screen.setdefault(owner, []).append(placed)
    return [ScreenLocators(owner, tuple(by_screen[owner])) for owner in sorted(by_screen)]


def build(graph: Graph, *, surface: str | None = None, screen: str | None = None) -> dict:
    book = LocatorBook.parse(graph_mod.build(graph, surface=surface))
    screens = screen_locators(book, screen)
    strategies = [placed.locator.strategy for entry in screens for placed in entry.locators]
    return {
        "screens": [entry.row() for entry in screens],
        "collisions": [item.row() for item in collisions(book)],
        "unnamed": [item.row() for item in unnamed_interactives(book)],
        "invalid_roles": [item.row() for item in invalid_roles(book)],
        "static_templates": [item.row() for item in static_templates(book)],
        "unproven_unique": [item.row() for item in unproven_unique_names(book)],
        "malformed_templates": [item.row() for item in malformed_templates(book)],
        "invalid_variants": [item.row() for item in invalid_variants(book)],
        "counts": {
            "locators": len(strategies),
            "by_role": strategies.count("role"),
            "by_template": strategies.count("template"),
            "by_css": strategies.count("css"),
            "by_scheme": strategies.count("scheme"),
            "unlocatable": strategies.count("none"),
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
