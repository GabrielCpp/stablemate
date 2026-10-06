"""The frame every obligation of a book node shares: its surface, journey, locators and repeat contract."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from ostler import markdown, registry
from ostler.qa.journey_steps import JourneyStep, journey_steps
from ostler.untyped import JsonValue

_LOCATOR_KEYS = tuple(sorted(registry.LOCATOR_KEYS))
_LOCATOR_KEY_RENAME = {"exclusive-with": "exclusiveWith"}


_SEGMENT_FIELDS = {"literal": "text", "bind": "path", "opaque": "expr"}


@dataclass(frozen=True, slots=True)
class Segment:
    """One compiled piece of a name template: literal text, a bound scope path, or an opaque expression."""

    kind: str
    value: str

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> Segment:
        """The segment a compiled locator carries, refusing a kind the compiler does not emit."""
        kind = str(raw.get("kind", ""))
        value_key = _SEGMENT_FIELDS.get(kind)
        value = raw.get(value_key) if value_key is not None else None
        if not isinstance(value, str):
            raise ValueError(f"a template segment has an unknown shape: {raw!r}")
        return cls(kind=kind, value=value)

    def row(self) -> dict[str, JsonValue]:
        """The segment as the obligation row carries it."""
        return {"kind": self.kind, _SEGMENT_FIELDS[self.kind]: self.value}


@dataclass(frozen=True, slots=True)
class RepeatTemplate:
    """The name template a repeated node's locator compiles to: its text, the scope it iterates, and its compiled segments."""

    template: str
    iterates: str
    segments: tuple[Segment, ...]

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> RepeatTemplate | None:
        """The template a repeat contract row carries, None when it carries none, refusing any other shape."""
        if raw.get("template") is None:
            return None
        template, iterates, segments = raw.get("template"), raw.get("iterates"), raw.get("segments")
        if not isinstance(template, str) or not isinstance(iterates, str) or not isinstance(segments, list):
            raise ValueError(f"a repeat template has an unknown shape: {raw!r}")
        parsed: list[Segment] = []
        for segment in segments:
            if not isinstance(segment, Mapping):
                raise ValueError(f"a template segment is not a mapping: {segment!r}")
            parsed.append(Segment.parse({str(key): value for key, value in segment.items()}))
        return cls(template=template, iterates=iterates, segments=tuple(parsed))


@dataclass(frozen=True, slots=True)
class Variants:
    """The enumerable variant axis of a repeated node: the dot-path it varies on and each value."""

    path: str
    values: tuple[str, ...]

    @classmethod
    def parse(cls, raw: object) -> Variants | None:
        """The variant axis an obligation row carries, None when the row states none, refusing any other shape."""
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise ValueError(f"a variant axis is not a mapping: {raw!r}")
        path, values = raw.get("path"), raw.get("values")
        if not isinstance(path, str) or not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"a variant axis has an unknown shape: {raw!r}")
        return cls(path=path, values=tuple(str(value) for value in values))

    def row(self) -> dict[str, JsonValue]:
        """The axis as the obligation row carries it."""
        return {"path": self.path, "values": [*self.values]}


@dataclass(frozen=True, slots=True)
class RepeatContract:
    """The contract of a node in a `one-per:` scope: what it repeats over, what its name binds, its template, what makes it distinct, and its variants."""

    one_per: str
    binds: tuple[str, ...]
    template: RepeatTemplate | None
    unique_by: str
    variants: Variants | None

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> RepeatContract:
        """The contract an obligation row carries, refusing a shape `row` does not write."""
        one_per, binds, unique_by = raw.get("onePer"), raw.get("binds", []), raw.get("uniqueBy", "")
        if (
            not isinstance(one_per, str)
            or not isinstance(binds, list)
            or not all(isinstance(bind, str) for bind in binds)
            or not isinstance(unique_by, str)
        ):
            raise ValueError(f"a repeat contract has an unknown shape: {raw!r}")
        return cls(
            one_per=one_per,
            binds=tuple(str(bind) for bind in binds),
            template=RepeatTemplate.parse(raw),
            unique_by=unique_by,
            variants=Variants.parse(raw.get("variants")),
        )

    def row(self) -> dict[str, JsonValue]:
        """The contract as the obligation row carries it, leaving out what the node does not state."""
        fields: dict[str, JsonValue] = {"onePer": self.one_per, "binds": [*self.binds]}
        if self.template is not None:
            fields["template"] = self.template.template
            fields["iterates"] = self.template.iterates
            fields["segments"] = [segment.row() for segment in self.template.segments]
        if self.unique_by:
            fields["uniqueBy"] = self.unique_by
        if self.variants is not None:
            fields["variants"] = self.variants.row()
        return fields


@dataclass(frozen=True, slots=True)
class ObligationFrame:
    """What every obligation of one node shares: the surface it is reached on, the steps of a flow, whether it sits on a cli page, the locators, whether an `extends:` arm failed to resolve, and the repeat contract."""

    surface: str
    steps: tuple[JourneyStep, ...]
    on_cli_page: bool
    locators: dict[str, list[str]]
    extends_unresolved: bool
    repeat: RepeatContract | None

    def row(self) -> dict[str, JsonValue]:
        """The frame as the obligation row carries it, leaving out what the node does not state."""
        fields: dict[str, JsonValue] = {}
        if self.surface:
            fields["surface"] = self.surface
        if self.steps:
            fields["steps"] = [step.row() for step in self.steps]
        if self.on_cli_page:
            fields["onCliPage"] = True
        if self.extends_unresolved:
            fields["extendsUnresolved"] = True
        if self.locators:
            fields["locators"] = {key: [*values] for key, values in self.locators.items()}
        if self.repeat is not None:
            fields["repeat"] = self.repeat.row()
        return fields


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


def property_text(value: object) -> str:
    """One serialized entry property as its text — the JSON-side twin of `Entry.property_text`."""
    if isinstance(value, list):
        return " ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() if value is not None else ""


@dataclass(frozen=True)
class NodeEntry:
    """One entry under a node's bullet: its headline, and each of its properties as text."""

    headline: str
    properties: Mapping[str, str]

    @classmethod
    def parse(cls, raw: object) -> NodeEntry | None:
        if not isinstance(raw, Mapping):
            return None
        fields = {str(key): value for key, value in raw.items()}
        properties = fields.get("properties")
        return cls(
            headline=str(fields.get("headline", "")),
            properties=(
                {str(key): property_text(value) for key, value in properties.items()}
                if isinstance(properties, Mapping)
                else {}
            ),
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
    path: str = ""
    title: str = ""
    line: int = 0
    bullet_order: tuple[tuple[str, str, int], ...] = ()
    combiners: Mapping[int, str] = field(default_factory=dict)
    kind: str = ""
    entries: Mapping[str, tuple[NodeEntry, ...]] = field(default_factory=dict)

    @classmethod
    def parse(cls, raw: Mapping[str, object]) -> BookNode:
        node_type = str(raw.get("type") or "")
        type_path = raw.get("type_path")
        bullets = raw.get("bullets")
        edges = raw.get("edges")
        line = raw.get("line")
        bullet_order = raw.get("bulletOrder")
        combiners = raw.get("combiners")
        entries = raw.get("entries")
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
            path=str(raw.get("path") or ""),
            title=str(raw.get("title") or ""),
            line=line if isinstance(line, int) else 0,
            bullet_order=(
                tuple(
                    (str(row[0]), str(row[1]), row[2])
                    for row in bullet_order
                    if isinstance(row, list | tuple) and len(row) == 3 and isinstance(row[2], int)
                )
                if isinstance(bullet_order, list)
                else ()
            ),
            combiners=(
                {int(str(position)): str(word) for position, word in combiners.items()}
                if isinstance(combiners, Mapping)
                else {}
            ),
            kind=str(raw.get("kind") or ""),
            entries=(
                {
                    str(key): tuple(entry for entry in map(NodeEntry.parse, value) if entry is not None)
                    for key, value in entries.items()
                    if isinstance(value, list)
                }
                if isinstance(entries, Mapping)
                else {}
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


@dataclass(frozen=True, slots=True)
class ExtendsResolution:
    """Where a node's `extends:` arm lands: the base node it inherits its control identity from, or None, and whether the arm names a base that is missing from the book or of another type."""

    target: BookNode | None
    unresolved: bool


def resolve_extends(node: BookNode, book: Mapping[str, BookNode]) -> ExtendsResolution:
    """The base node an `extends:` arm inherits its control identity from (D51)."""
    to_ids = [edge.to for edge in node.edges if edge.via == "extends" and edge.to]
    if not to_ids:
        return ExtendsResolution(target=None, unresolved=False)
    target = book.get(to_ids[0])
    if target is None or target.type != node.type:
        return ExtendsResolution(target=None, unresolved=True)
    return ExtendsResolution(target=target, unresolved=False)


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


def obligation_frame(
    node: BookNode, repeat: RepeatContract | None, book: Mapping[str, BookNode]
) -> ObligationFrame:
    """The frame every obligation of *node* shares."""
    surface, steps = "", ()
    if node.type == "flow":
        surface = linked_surface(node, node.bullets.get("end", ()), book)
        steps = journey_steps(node, book)
    locators = declared_locators(node)
    extends_unresolved = False
    if node.type in ("interaction", "invocation"):
        extends = resolve_extends(node, book)
        if extends.target is not None:
            locators = {**declared_locators(extends.target), **locators}
        extends_unresolved = extends.unresolved
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
