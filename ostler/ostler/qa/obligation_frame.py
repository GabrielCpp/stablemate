"""The frame every obligation of a book node shares: its surface, journey, locators and repeat contract."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ostler import markdown, registry
from ostler.qa.packet_rows import JourneyStep, ObligationFrame, RepeatContract

_LOCATOR_KEYS = tuple(sorted(registry.LOCATOR_KEYS))
_LOCATOR_KEY_RENAME = {"exclusive-with": "exclusiveWith"}


def bullet_values(value: object) -> list[str]:
    """A bullet's values as the graph serialized them: one string or a list of them."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


@dataclass(frozen=True)
class NodeEdge:
    """One outgoing edge of a book node: the node it reaches, the bullet it came from and the link it was."""

    to: str
    via: str
    href: str

    @classmethod
    def parse(cls, raw: object) -> NodeEdge | None:
        if not isinstance(raw, Mapping):
            return None
        fields = {str(key): value for key, value in raw.items()}
        return cls(
            to=str(fields.get("to") or ""),
            via=str(fields.get("via") or ""),
            href=str(fields.get("href") or ""),
        )


@dataclass(frozen=True)
class BookNode:
    """The parts of a serialized book node the obligation frame reads."""

    id: str
    type: str
    page_type: str
    surface: str
    bullets: Mapping[str, tuple[str, ...]]
    edges: tuple[NodeEdge, ...]

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> BookNode:
        node_type = str(raw.get("type") or "")
        type_path = raw.get("type_path")
        bullets = raw.get("bullets")
        edges = raw.get("edges")
        return cls(
            id=str(raw.get("id") or ""),
            type=node_type,
            page_type=str(type_path[0]) if isinstance(type_path, list) and type_path else node_type,
            surface=str(raw.get("surface") or ""),
            bullets=(
                {str(key): tuple(bullet_values(value)) for key, value in bullets.items()}
                if isinstance(bullets, Mapping)
                else {}
            ),
            edges=(
                tuple(edge for edge in map(NodeEdge.parse, edges) if edge is not None)
                if isinstance(edges, list)
                else ()
            ),
        )

    def targets(self, via: str, book: Mapping[str, BookNode]) -> list[BookNode]:
        """The nodes this node's *via* bullet resolves to, in document order."""
        return [book[edge.to] for edge in self.edges if edge.via == via and edge.to in book]


def book_nodes(raw_nodes: Mapping[str, Mapping[str, object]]) -> dict[str, BookNode]:
    """Every serialized node of a book, parsed once where the graph enters."""
    return {node_id: BookNode.parse(raw) for node_id, raw in raw_nodes.items()}


def declared_locators(node: BookNode) -> dict[str, list[str]]:
    """The locator bullets *node*'s type declares, keyed the way the packet spells them."""
    declared = registry.declared_keys(node.type)
    return {
        _LOCATOR_KEY_RENAME.get(key, key): list(node.bullets[key])
        for key in _LOCATOR_KEYS
        if key in declared and node.bullets.get(key)
    }


def extends_target(node: BookNode, book: Mapping[str, BookNode]) -> tuple[BookNode | None, bool]:
    """The base node an `extends:` arm inherits its control identity from (D51)."""
    to_ids = [edge.to for edge in node.edges if edge.via == "extends" and edge.to]
    if not to_ids:
        return None, False
    target = book.get(to_ids[0])
    if target is None or target.type != node.type:
        return None, True
    return target, False


def _endpoint_address(node: BookNode, book: Mapping[str, BookNode]) -> dict[str, list[str]]:
    """The address of the endpoint an invocation's `on:` names, which the invocation calls."""
    for target in node.targets("on", book):
        if target.type == "endpoint":
            located = declared_locators(target)
            return {key: located[key] for key in registry.address_keys("endpoint") if key in located}
    return {}


def linked_surface(node: BookNode, values: Iterable[str], book: Mapping[str, BookNode]) -> str:
    """The surface of the node *values*' own links point at — "" when they point at none."""
    hrefs = {href for item in values for _text, href in markdown.extract_refs(item).links}
    if not hrefs:
        return ""
    for edge in node.edges:
        if not edge.to or edge.href not in hrefs:
            continue
        target = book.get(edge.to)
        if target and target.surface:
            return target.surface
    return ""


def _journey_steps(node: BookNode, book: Mapping[str, BookNode]) -> tuple[JourneyStep, ...]:
    """The nodes a flow's `steps:` names, in the order the book wrote them."""
    resolved = {edge.href: edge.to for edge in node.edges if edge.to and edge.href}
    walk: list[JourneyStep] = []
    for item in node.bullets.get("steps", ()):
        for _text, href in markdown.extract_refs(item).links:
            target_id = resolved.get(href, "")
            target = book.get(target_id) if target_id else None
            walk.append(
                JourneyStep(
                    ref=target_id,
                    href=href,
                    node_type=target.type if target else "",
                    surface=target.surface if target else "",
                )
            )
    return tuple(walk)


def obligation_frame(
    node: BookNode, repeat: RepeatContract | None, book: Mapping[str, BookNode]
) -> ObligationFrame:
    """The frame every obligation of *node* shares."""
    surface, steps = "", ()
    if node.type == "flow":
        surface = linked_surface(node, node.bullets.get("end", ()), book)
        steps = _journey_steps(node, book)
    locators = declared_locators(node)
    extends_unresolved = False
    if node.type in ("interaction", "invocation"):
        base, extends_malformed = extends_target(node, book)
        if base is not None:
            locators = {**declared_locators(base), **locators}
        else:
            extends_unresolved = extends_malformed
    if node.type == "invocation":
        locators = {**_endpoint_address(node, book), **locators}
    return ObligationFrame(
        surface=surface,
        steps=steps,
        on_cli_page=node.page_type == "cli",
        locators=locators,
        extends_unresolved=extends_unresolved,
        repeat=repeat,
    )
