"""The typed rows the QA context packet carries: health findings about the book, and what each obligation of a node shares."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ostler import locators as locators_mod
from ostler import markdown, refs as refs_mod, registry

RELATION_FANOUT = 6


def bullet_values(value: Any) -> list[str]:
    """A bullet's values as strings: each item of a list, or the one value when it is set."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


@dataclass(frozen=True, slots=True)
class HealthRow:
    """One health finding about the book, as the packet's health lists it once serialized."""

    kind: str
    severity: str
    message: str
    node: str = ""
    ref: str = ""
    key: str = ""

    def row(self) -> dict[str, str]:
        """The finding as the packet lists it, leaving out the fields it does not name."""
        named = {"node": self.node, "ref": self.ref, "key": self.key}
        return {"kind": self.kind, "severity": self.severity, **{name: value for name, value in named.items() if value}, "message": self.message}


def resolve_groundings(
    nodes: dict[str, dict[str, Any]], resolves: Callable[[str], bool]
) -> tuple[set[str], list[HealthRow]]:
    """The nodes with a code citation that resolves, and a health row per citation that resolves nowhere. Each distinct citation is resolved once."""
    grounded: set[str] = set()
    dangling: list[HealthRow] = []
    ref_resolves: dict[str, bool] = {}
    for node_id, node in nodes.items():
        for normalized in refs_mod.code_refs(node.get("bullets", {}).get("code")):
            if normalized not in ref_resolves:
                ref_resolves[normalized] = resolves(normalized)
            if ref_resolves[normalized]:
                grounded.add(node_id)
            else:
                dangling.append(
                    HealthRow(
                        kind="dangling-grounding",
                        severity="error",
                        node=node_id,
                        ref=normalized,
                        message="code grounding resolves in neither base nor head",
                    )
                )
    return grounded, dangling


def missing_declared_checks(node_id: str, node: dict[str, Any]) -> list[HealthRow]:
    """A health row per normative claim of a checked node type that declares no check to fulfil it."""
    node_type = str(node.get("type", ""))
    if not registry.check_keys(node_type):
        return []
    node_bullets = node.get("bullets", {})
    combiners = {int(pos): str(word) for pos, word in (node.get("combiners") or {}).items()}
    _, checks_per_bullet = registry.attributed_checks(node_type, node.get("bulletOrder") or [], combiners)
    return [
        HealthRow(
            kind="missing-declared-check",
            severity="warning",
            node=node_id,
            key=key,
            message=f"impacted contract's `{key}:` claim declares no `verify:` check to fulfil it",
        )
        for key in registry.normative_keys(node_type)
        for index in range(1, len(bullet_values(node_bullets.get(key))) + 1)
        if not checks_per_bullet.get((key, index))
    ]


def relation_fanout(subjects_by_node: dict[str, set[str]], required_subjects: set[str]) -> list[HealthRow]:
    """A health row per required relation subject that more nodes name than a change can owe evidence for."""
    owners_by_subject: dict[str, list[str]] = {}
    for node_id, subjects in subjects_by_node.items():
        for subject in subjects & required_subjects:
            owners_by_subject.setdefault(subject, []).append(node_id)
    return [
        HealthRow(
            kind="relation-fanout",
            severity="warning",
            ref=subject,
            message=(
                f"relation subject `{subject}` binds {len(owners_by_subject[subject])} nodes; a change"
                " reaching any of them owes live evidence for all of them, which"
                " usually means the subject is named more broadly than the record"
            ),
        )
        for subject in sorted(required_subjects)
        if len(owners_by_subject.get(subject, [])) > RELATION_FANOUT
    ]


@dataclass(frozen=True, slots=True)
class JourneyStep:
    """One node a flow's `steps:` names: its id, the link the book wrote, its type and its surface."""

    ref: str
    href: str
    node_type: str
    surface: str

    def row(self) -> dict[str, str]:
        """The step as the obligation row carries it."""
        return {"ref": self.ref, "href": self.href, "nodeType": self.node_type, "surface": self.surface}


def journey_steps(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> tuple[JourneyStep, ...]:
    """The nodes a flow's `steps:` names, in the order the book wrote them."""
    resolved = {
        str(edge["href"]): str(edge["to"])
        for edge in node.get("edges") or []
        if edge.get("to") and edge.get("href")
    }
    walk: list[JourneyStep] = []
    for item in bullet_values(node.get("bullets", {}).get("steps")):
        for _text, href in markdown.extract_refs(item).links:
            target_id = resolved.get(href, "")
            target = nodes_by_id.get(target_id, {}) if target_id else {}
            walk.append(
                JourneyStep(
                    ref=target_id,
                    href=href,
                    node_type=str(target.get("type") or ""),
                    surface=str(target.get("surface") or ""),
                )
            )
    return tuple(walk)


_SEGMENT_FIELDS = {"literal": "text", "bind": "path", "opaque": "expr"}


@dataclass(frozen=True, slots=True)
class Segment:
    """One compiled piece of a name template: literal text, a bound scope path, or an opaque expression."""

    kind: str
    value: str

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Segment:
        """The segment a compiled locator carries, refusing a kind the compiler does not emit."""
        kind = str(raw.get("kind", ""))
        field = _SEGMENT_FIELDS.get(kind)
        if field is None or not isinstance(raw.get(field), str):
            raise ValueError(f"a template segment has an unknown shape: {raw!r}")
        return cls(kind=kind, value=raw[field])

    def row(self) -> dict[str, str]:
        """The segment as the obligation row carries it."""
        return {"kind": self.kind, _SEGMENT_FIELDS[self.kind]: self.value}


@dataclass(frozen=True, slots=True)
class RepeatTemplate:
    """The name template a repeated node's locator compiles to: its text, the scope it iterates, and its compiled segments."""

    template: str
    iterates: str
    segments: tuple[Segment, ...]


@dataclass(frozen=True, slots=True)
class Variants:
    """The enumerable variant axis of a repeated node: the dot-path it varies on and each value."""

    path: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepeatContract:
    """The contract of a node in a `one-per:` scope: what it repeats over, what its name binds, its template, what makes it distinct, and its variants."""

    one_per: str
    binds: tuple[str, ...]
    template: RepeatTemplate | None
    unique_by: str
    variants: Variants | None

    def row(self) -> dict[str, Any]:
        """The contract as the obligation row carries it, leaving out what the node does not state."""
        fields: dict[str, Any] = {"onePer": self.one_per, "binds": list(self.binds)}
        if self.template is not None:
            fields["template"] = self.template.template
            fields["iterates"] = self.template.iterates
            fields["segments"] = [segment.row() for segment in self.template.segments]
        if self.unique_by:
            fields["uniqueBy"] = self.unique_by
        if self.variants is not None:
            fields["variants"] = {"path": self.variants.path, "values": list(self.variants.values)}
        return fields


def repeat_contract(node: dict[str, Any], scope: tuple[str, ...]) -> RepeatContract | None:
    """The compiled repeat contract for a node in a `one-per:` scope, or None."""
    own = locators_mod.repeat_of(node)
    scope = scope or ((own,) if own else ())
    if not scope:
        return None
    located = locators_mod.locator_for(node, scope=scope)
    template, binds = None, ()
    if located["strategy"] == "template":
        template = RepeatTemplate(
            template=str(located["template"]),
            iterates=str(located["iterates"]),
            segments=tuple(Segment.parse(segment) for segment in located["segments"]),
        )
        binds = tuple(str(bind) for bind in located["binds"])
    variants = locators_mod.variants_of(node)
    return RepeatContract(
        one_per=scope[-1],
        binds=binds,
        template=template,
        unique_by=locators_mod.unique_by_of(node),
        variants=Variants(path=str(variants["path"]), values=tuple(variants["values"])) if variants else None,
    )


@dataclass(frozen=True, slots=True)
class ObligationFrame:
    """What every obligation of one node shares: the surface it is reached on, the steps of a flow, whether it sits on a cli page, the locators, whether an `extends:` arm failed to resolve, and the repeat contract."""

    surface: str
    steps: tuple[JourneyStep, ...]
    on_cli_page: bool
    locators: dict[str, list[str]]
    extends_unresolved: bool
    repeat: RepeatContract | None

    def row(self) -> dict[str, Any]:
        """The frame as the obligation row carries it, leaving out what the node does not state."""
        fields: dict[str, Any] = {}
        if self.surface:
            fields["surface"] = self.surface
        if self.steps:
            fields["steps"] = [step.row() for step in self.steps]
        if self.on_cli_page:
            fields["onCliPage"] = True
        if self.extends_unresolved:
            fields["extendsUnresolved"] = True
        if self.locators:
            fields["locators"] = self.locators
        if self.repeat is not None:
            fields["repeat"] = self.repeat.row()
        return fields
