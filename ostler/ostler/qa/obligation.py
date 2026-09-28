"""One obligation of the context packet, read once into typed records where the compiler takes it in."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import fields
from typing import Any

from ostler.checks import CheckValue


@dataclass(frozen=True)
class Locators:
    """A node's own locator bullets, each the raw values the book states for it, in book order."""
    route: tuple[str, ...] = ()
    method: tuple[str, ...] = ()
    path: tuple[str, ...] = ()
    channel: tuple[str, ...] = ()
    entry: tuple[str, ...] = ()
    params: tuple[str, ...] = ()
    role: tuple[str, ...] = ()
    name: tuple[str, ...] = ()
    selector: tuple[str, ...] = ()
    keyboard: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    on: tuple[str, ...] = ()
    trigger: tuple[str, ...] = ()
    does: tuple[str, ...] = ()
    when: tuple[str, ...] = ()
    exclusive_with: tuple[str, ...] = ()


NO_LOCATORS = Locators()

_LOCATOR_FIELDS = frozenset(field.name for field in fields(Locators))

_PACKET_LOCATOR_KEYS = {"exclusiveWith": "exclusive_with"}


@dataclass(frozen=True)
class LocatedNode:
    """The book node a locator argument resolved to, and that node's own locator bullets."""
    node: str
    locators: Locators


@dataclass(frozen=True)
class CallRow:
    """One parsed `verify:` or `arrange:` call: its name, canonical spelling, arguments and resolved locators."""
    name: str
    call: str
    args: dict[str, CheckValue]
    locates: dict[str, LocatedNode]

    def text_arg(self, key: str) -> str:
        """Argument *key* as text, empty when the call does not state it."""
        value = self.args.get(key)
        return "" if value is None else str(value)

    def list_arg(self, key: str) -> list[str]:
        """Argument *key* as a list of strings, empty when the call does not state it."""
        value = self.args.get(key)
        return [str(item) for item in value] if isinstance(value, list) else []


@dataclass(frozen=True)
class CaptureRow:
    """One `capture: <name> from <source>` declaration."""
    name: str
    source: str


@dataclass(frozen=True)
class FixtureRow:
    """One `fixture:` reference: the arrangement's name, its arguments, and the keys it provides."""
    name: str
    args: tuple[str, ...]
    provides: str
    provides_keys: tuple[str, ...]
    provides_undetermined: tuple[str, ...]

    @property
    def precondition(self) -> str:
        """What a scenario's `preconditions=` names this arrangement by."""
        return self.provides or self.name


@dataclass(frozen=True)
class UnparsedRow:
    """A bullet the book parser read and refused: its text and the parser's own account."""
    value: str
    problem: str


@dataclass(frozen=True)
class FlowStep:
    """One entry of a flow's `steps:`: the node it resolved to, the link the book wrote, and where that node lives."""
    ref: str
    href: str
    node_type: str
    surface: str


@dataclass(frozen=True)
class Obligation:
    """One owed claim of the context packet, with every declaration a plan builder reads."""
    id: str
    required: bool
    kind: str
    node: str
    node_type: str
    on_cli_page: bool
    source: str
    surface: str
    requirement: str
    doc_position: tuple[int, ...]
    locators: Locators
    checks: tuple[CallRow, ...]
    acts: tuple[CallRow, ...]
    captures: tuple[CaptureRow, ...]
    fixtures: tuple[FixtureRow, ...]
    steps: tuple[FlowStep, ...]
    arranges_nothing: bool
    combiner_unstated: bool
    extends_unresolved: bool
    checks_unparsed: tuple[UnparsedRow, ...]
    acts_unparsed: tuple[UnparsedRow, ...]
    fixtures_unparsed: tuple[UnparsedRow, ...]
    captures_unparsed: tuple[UnparsedRow, ...]


def _mapping(value: object, what: str) -> Mapping[str, object]:
    """*value* as a mapping, refused loudly when the packet carries anything else."""
    if not isinstance(value, dict):
        raise ValueError(f"{what} is not a mapping: {value!r}")
    return {str(key): item for key, item in value.items()}


def _rows(value: object, what: str) -> list[Mapping[str, object]]:
    """A packet list of mappings, empty when the packet left it unset."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{what} is not a list: {value!r}")
    return [_mapping(item, f"a {what} entry") for item in value]


def _text(row: Mapping[str, object], key: str) -> str:
    """One string field of a packet row, empty when unset and refused when anything else."""
    value = row.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"packet field {key!r} is not a string: {dict(row)!r}")
    return value


def _texts(value: object, what: str) -> tuple[str, ...]:
    """A packet list of strings as a tuple, empty when unset, refused loudly when anything else."""
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{what} is not a list of strings: {value!r}")
    return tuple(item for item in value if isinstance(item, str))


def _flag(row: Mapping[str, object], key: str, *, default: bool) -> bool:
    """One boolean field of a packet row, *default* when unset and refused when anything else."""
    value = row.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"packet field {key!r} is not a boolean: {dict(row)!r}")
    return value


def _locators(value: object) -> Locators:
    """A node's locator bullets, refused loudly when the packet names a bullet no locator carries."""
    if value is None:
        return NO_LOCATORS
    bullets: dict[str, tuple[str, ...]] = {}
    for key, values in _mapping(value, "`locators`").items():
        name = _PACKET_LOCATOR_KEYS.get(key, key)
        if name not in _LOCATOR_FIELDS:
            raise ValueError(f"`locators` names {key!r}, which is not a locator bullet")
        bullets[name] = _texts(values, f"locator {key!r}")
    return Locators(**bullets)


def _check_value(value: object, what: str) -> CheckValue:
    """One call argument, refused loudly when it is not a literal the call grammar spells."""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return list(_texts(value, what))
    raise ValueError(f"{what} is not a call literal: {value!r}")


def _call_row(row: Mapping[str, object]) -> CallRow:
    """One `checksDeclared` or `actsDeclared` entry."""
    args = _mapping(row.get("args") or {}, "call `args`")
    locates = _mapping(row.get("locates") or {}, "call `locates`")
    return CallRow(
        name=_text(row, "name"),
        call=_text(row, "call"),
        args={key: _check_value(value, f"argument {key!r}") for key, value in args.items()},
        locates={
            param: LocatedNode(
                node=_text(target, "node"), locators=_locators(target.get("locators")))
            for param, target in (
                (param, _mapping(raw or {}, f"locator {param!r}")) for param, raw in locates.items())
        },
    )


def _fixture_row(row: Mapping[str, object]) -> FixtureRow:
    """One `fixturesDeclared` entry."""
    return FixtureRow(
        name=_text(row, "name"),
        args=_texts(row.get("args"), "fixture `args`"),
        provides=_text(row, "provides"),
        provides_keys=_texts(row.get("providesKeys"), "fixture `providesKeys`"),
        provides_undetermined=_texts(row.get("providesUndetermined"), "fixture `providesUndetermined`"),
    )


def _flow_step(step: Mapping[str, object]) -> FlowStep:
    """One `steps` entry."""
    return FlowStep(
        ref=_text(step, "ref"), href=_text(step, "href"),
        node_type=_text(step, "nodeType"), surface=_text(step, "surface"),
    )


def _unparsed(value: object, what: str) -> tuple[UnparsedRow, ...]:
    """A packet list of refused bullets."""
    return tuple(UnparsedRow(value=_text(row, "value"), problem=_text(row, "problem"))
                 for row in _rows(value, what))


def _position(value: object) -> tuple[int, ...]:
    """A packet `docPosition`, `(0, 0)` when the packet left it unset, refused when not a list of ints."""
    if value is None or value == []:
        return (0, 0)
    if not isinstance(value, list):
        raise ValueError(f"context `docPosition` is not a list: {value!r}")
    position: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"context `docPosition` holds {item!r}; every item must be an int")
        position.append(item)
    return tuple(position)


def obligation_of(raw: Mapping[str, Any]) -> Obligation:
    """One packet obligation, refused loudly when a field it declares is malformed."""
    row = _mapping(dict(raw), "an obligation")
    return Obligation(
        id=_text(row, "id"),
        required=_flag(row, "required", default=True),
        kind=_text(row, "kind"),
        node=_text(row, "node"),
        node_type=_text(row, "nodeType"),
        on_cli_page=_flag(row, "onCliPage", default=False),
        source=_text(row, "source"),
        surface=_text(row, "surface"),
        requirement=_text(row, "requirement"),
        doc_position=_position(row.get("docPosition")),
        locators=_locators(row.get("locators")),
        checks=tuple(_call_row(item) for item in _rows(row.get("checksDeclared"), "`checksDeclared`")),
        acts=tuple(_call_row(item) for item in _rows(row.get("actsDeclared"), "`actsDeclared`")),
        captures=tuple(
            CaptureRow(name=_text(item, "name"), source=_text(item, "from"))
            for item in _rows(row.get("capturesDeclared"), "`capturesDeclared`")),
        fixtures=tuple(
            _fixture_row(item) for item in _rows(row.get("fixturesDeclared"), "`fixturesDeclared`")),
        steps=tuple(_flow_step(item) for item in _rows(row.get("steps"), "flow `steps`")),
        arranges_nothing=_flag(row, "arrangesNothing", default=False),
        combiner_unstated=row.get("claimCombiner") == "unstated",
        extends_unresolved=_flag(row, "extendsUnresolved", default=False),
        checks_unparsed=_unparsed(row.get("checksUnparsed"), "`checksUnparsed`"),
        acts_unparsed=_unparsed(row.get("actsUnparsed"), "`actsUnparsed`"),
        fixtures_unparsed=_unparsed(row.get("fixturesUnparsed"), "`fixturesUnparsed`"),
        captures_unparsed=_unparsed(row.get("capturesUnparsed"), "`capturesUnparsed`"),
    )


def obligations_of(value: object) -> tuple[Obligation, ...]:
    """The packet's `obligations`, every one validated, refused loudly when the list is malformed."""
    return tuple(obligation_of(row) for row in _rows(value, "`obligations`"))
