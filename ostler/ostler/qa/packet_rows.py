"""The typed rows the QA context packet carries: health findings about the book, and what each obligation of a node shares."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


RELATION_FANOUT = 6


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
    code_refs_by_node: dict[str, tuple[str, ...]], resolves: Callable[[str], bool]
) -> tuple[set[str], list[HealthRow]]:
    """The nodes with a code citation that resolves, and a health row per citation that resolves nowhere. Each distinct citation is resolved once."""
    grounded: set[str] = set()
    dangling: list[HealthRow] = []
    ref_resolves: dict[str, bool] = {}
    for node_id, code_refs in code_refs_by_node.items():
        for normalized in code_refs:
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


def relation_fanout_warnings(subjects_by_node: dict[str, set[str]], required_subjects: set[str]) -> list[HealthRow]:
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
        field = _SEGMENT_FIELDS.get(kind)
        value = raw.get(field) if field is not None else None
        if not isinstance(value, str):
            raise ValueError(f"a template segment has an unknown shape: {raw!r}")
        return cls(kind=kind, value=value)

    def row(self) -> dict[str, str]:
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

    def row(self) -> dict[str, Any]:
        """The axis as the obligation row carries it."""
        return {"path": self.path, "values": list(self.values)}


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
