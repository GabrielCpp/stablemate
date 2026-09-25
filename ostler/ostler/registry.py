"""The machine-readable type registry — the single source of truth for the knowledge format."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SEED_STATUSES = ("backlog", "researched", "covered", "resolved", "dropped", "deferred")
INACTIVE_SEED_STATUS = {"resolved", "dropped", "deferred"}
DEFAULT_SEED_STATUS = "backlog"

SEED_LAYERS = ("frontend", "backend", "infra")
SEED_DESIGNS = ("required", "preserve")

SEEDS_HEADING = "Seeds"
STORIES_HEADING = "Stories"

SEED_META_KEYS = (
    "status", "surface", "legacySurface", "backing", "prerequisites", "sourceBullet",
    "layers", "services", "design",
)
SEED_LIST_META_KEYS = ("layers", "services")
STORY_COVERS_KEY = "covers"
STORY_META_KEYS = (STORY_COVERS_KEY, "title", "id", "phase", "effort")

EMPTY_TOKENS = {"", "(none)", "none", "-", "—"}


@dataclass(frozen=True)
class SectionSpec:
    """One required ``## Heading`` in a document body."""
    heading: str
    filled: bool = False
    stub: str = ""


STORY_STATUS_HEADING = "Implementation Status"
STORY_STATUS_LABEL = "Status"
DEFAULT_STORY_STATUS = "Not started"

STORY_DEPS_HEADING = "Dependencies"
STORY_DEPS_LABEL = "Blocked by"
STORY_DEPS_NONE = "(none)"

STORY_FIXTURES_HEADING = "Fixtures"
STORY_FIXTURES_LABEL = "Fixture"
STORY_FIXTURES_NONE = "(none)"

STORY_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec(STORY_DEPS_HEADING, filled=False, stub=STORY_DEPS_NONE),
    SectionSpec(STORY_FIXTURES_HEADING, filled=False, stub=STORY_FIXTURES_NONE),
    SectionSpec("Context", filled=True),
    SectionSpec("Acceptance Criteria", filled=True),
    SectionSpec("Non-Functional Acceptance Criteria", filled=True),
    SectionSpec("Technical Notes", filled=True),
    SectionSpec(STORY_STATUS_HEADING, filled=False,
                stub=f"- **{STORY_STATUS_LABEL}**: {DEFAULT_STORY_STATUS}"),
)

RESERVED_FILES = {"index.md", "log.md"}


EPIC_SEQ_WIDTH = 4
EPIC_DIR_RE = re.compile(r"^(\d{4,})-(.+)$")


def epic_seq(name: str) -> int | None:
    """The sequence number of an epic directory name, or None when it carries no prefix."""
    m = EPIC_DIR_RE.match(name.strip())
    return int(m.group(1)) if m else None


def epic_slug(name: str) -> str:
    """The slug half of an epic directory name — the whole name when it has no prefix."""
    m = EPIC_DIR_RE.match(name.strip())
    return m.group(2) if m else name.strip()


def epic_dir_name(seq: int, slug: str) -> str:
    """The directory name for the *seq*-th epic: ``0001-checkout-flow``."""
    return f"{seq:0{EPIC_SEQ_WIDTH}d}-{slug}"


def next_epic_seq(names: Iterable[str]) -> int:
    """The number the next epic directory takes: one past the highest currently on disk."""
    taken = [n for n in (epic_seq(x) for x in names) if n is not None]
    return max(taken, default=0) + 1


@dataclass(frozen=True)
class EntityType:
    """One Concept type in the knowledge format."""
    name: str
    doc_root: str
    location: str
    required: tuple[str, ...] = ()
    schema: str | None = None
    note: str = ""


REGISTRY: tuple[EntityType, ...] = (
    EntityType(
        name="epic", doc_root="epics", location="*/epic.md",
        required=("type", "id", "title"), schema="epic.schema.json",
        note="Source of truth for an epic: narrative + `## Seeds` + `## Stories` (the DAG).",
    ),
    EntityType(
        name="milestone", doc_root="milestones", location="*.md",
        required=("type", "id", "title"), schema="milestone.schema.json",
        note="Product/workflow milestone: a dependency-ordered group of epics.",
    ),
    EntityType(
        name="story", doc_root="epics", location="*/stories/*/story.md",
        required=("type", "slug", "status"), schema="story.schema.json",
        note="Leaf story spec. Edges (covers/depends) live in the epic's `## Stories` section.",
    ),
    EntityType(
        name="feature", doc_root="features", location="**/*.md",
        required=("type", "slug", "title"), schema="feature.schema.json",
        note="Per-surface feature doc; the inventory is derived from these.",
    ),
    EntityType(
        name="spec", doc_root="specs", location="*/*.md",
        required=("type",), schema=None,
        note="Coder process artifact (spec.<stem>: spec.plan, spec.qa, …). Conformance only.",
    ),
)

REGISTRY_BY_NAME: dict[str, EntityType] = {t.name: t for t in REGISTRY}


@dataclass(frozen=True)
class BulletKey:
    """One recognized metadata bullet inside a UI node (``- key: value``)."""
    key: str
    required: bool = False
    nested: bool = False
    record: bool = False
    entries: bool = False
    link: bool = False
    check: bool = False
    arrange: bool = False
    performs: bool = False
    normative: bool = False
    alias: bool = False
    refusal: bool = False
    owns: bool = False
    capture: bool = False
    locator: bool = False
    condition: bool = False
    address: bool = False
    properties: tuple[str, ...] = ()
    value_kind: str = ""


@dataclass(frozen=True)
class UINodeType:
    """One UI-profile node type."""
    name: str
    kind: str
    doc_root: str = "features"
    heading: str = ""
    context: str = ""
    required_sections: tuple[SectionSpec, ...] = ()
    bullet_keys: tuple[BulletKey, ...] = ()
    body_template: str = ""
    literal_id: bool = False

    @property
    def bullet_by_key(self) -> dict[str, BulletKey]:
        return {b.key: b for b in self.bullet_keys}


CODE_GROUNDING_KEYS = frozenset({"code"})
RELATION_KEYS = ("on", "parent", "extends", "same-as", "steps", "presents", "detail",
                 "environment", "cli", "surfaces", "launch-screen", "requires", "params",
                 "leads-to", "exclusive-with", "prefers", "deprecates")

SHARED_NORMATIVE_KEYS = ("consistency", "consistency rule", "consistency group", "persistence",
                         "emits", "consumes", "concurrency", "idempotency")

SHARED_ADVISORY_KEYS = ("unspecified", "known-defect")


def normative_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` that becomes an obligation."""
    return SHARED_NORMATIVE_KEYS + NORMATIVE_KEYS_BY_TYPE.get(node_type, ())


def declared_keys(node_type: str) -> frozenset[str]:
    """Every bullet key `node_type` recognizes: its own declared bullets plus the keys that are normative on every type, plus `code:` (`CODE_GROUNDING_KEYS`) — which, like `owning_keys`' copy of the same set, is declared on every type whether or not that type's own profile lists it."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    own = () if uitype is None else uitype.bullet_keys
    return (
        frozenset(b.key for b in own)
        | frozenset(SHARED_NORMATIVE_KEYS)
        | frozenset(SHARED_ADVISORY_KEYS)
        | CODE_GROUNDING_KEYS
    )


def unknown_bullet_keys(node_type: str, keys: Iterable[str]) -> list[str]:
    """Which of `keys` `doctor`'s `unknown-bullet` would flag on a node typed `node_type`."""
    if node_type == "untyped":
        return []
    declared = declared_keys(node_type)
    return [key for key in keys if key not in declared and key in LOAD_BEARING_KEYS]


def owning_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` whose value names a file the node is documented against."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    own = () if uitype is None else tuple(b.key for b in uitype.bullet_keys if b.owns)
    return tuple(dict.fromkeys(tuple(sorted(CODE_GROUNDING_KEYS)) + own))


def check_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` whose value is a named check (`ostler.checks`)."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    return () if uitype is None else tuple(b.key for b in uitype.bullet_keys if b.check)


def fixture_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` whose value names a fixture this repo declares."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    return () if uitype is None else tuple(b.key for b in uitype.bullet_keys if b.arrange)


def performed_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` whose value is an act the performer carries out."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    return () if uitype is None else tuple(b.key for b in uitype.bullet_keys if b.performs)


def arrange_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` whose value arranges the state a claim is about."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    return () if uitype is None else tuple(
        b.key for b in uitype.bullet_keys if b.arrange or b.performs)


def condition_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` that names a state a claim holds *under*, not the claim."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    return () if uitype is None else tuple(b.key for b in uitype.bullet_keys if b.condition)


def address_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` that names where to reach the node, not a claim about it."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    return () if uitype is None else tuple(b.key for b in uitype.bullet_keys if b.address)


def refusal_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` that states the arm a claim is refused in, not performed in."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    return () if uitype is None else tuple(b.key for b in uitype.bullet_keys if b.refusal)


def attributed_fixtures(
    node_type: str, bullet_order: Iterable[Sequence[Any]], combiners: Mapping[int, str]
) -> tuple[list[str], dict[tuple[str, int], list[str]]]:
    """Split a node's fixture bullets between the node and the claims they arrange for."""
    return _attributed(node_type, bullet_order, combiners, fixture_keys(node_type))


def attributed_acts(
    node_type: str, bullet_order: Iterable[Sequence[Any]], combiners: Mapping[int, str]
) -> tuple[list[str], dict[tuple[str, int], list[str]]]:
    """Split a node's performed-arrangement bullets between the node and the claims they arrange."""
    return _attributed(node_type, bullet_order, combiners, performed_keys(node_type))


def capture_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` whose value captures a fact for later reference."""
    uitype = UI_TYPES_BY_NAME.get(node_type)
    return () if uitype is None else tuple(b.key for b in uitype.bullet_keys if b.capture)


def attached_keys(node_type: str) -> tuple[str, ...]:
    """Every bullet key on `node_type` that document order binds to a normative bullet above it."""
    return tuple(dict.fromkeys(
        check_keys(node_type) + arrange_keys(node_type) + capture_keys(node_type)))


def attributed_captures(
    node_type: str, bullet_order: Iterable[Sequence[Any]], combiners: Mapping[int, str]
) -> tuple[list[str], dict[tuple[str, int], list[str]]]:
    """Split a node's capture bullets between the node and the claims they were captured under."""
    return _attributed(node_type, bullet_order, combiners, capture_keys(node_type))


def attributed_checks(
    node_type: str, bullet_order: Iterable[Sequence[Any]], combiners: Mapping[int, str]
) -> tuple[list[str], dict[tuple[str, int], list[str]]]:
    """Split a node's check bullets between the contract and the claims they observe."""
    return _attributed(node_type, bullet_order, combiners, check_keys(node_type))


def attributed_check_bullets(
    node_type: str, bullet_order: Iterable[Sequence[Any]], combiners: Mapping[int, str]
) -> tuple[list[tuple[int, str]], dict[tuple[str, int], list[tuple[int, str]]]]:
    """`attributed_checks`, keeping each check's own authored `verify:` index beside its value."""
    return _attributed_indexed(node_type, bullet_order, combiners, check_keys(node_type))


_SELF_DECLARABLE_EMPTY_KEYS: frozenset[str] = frozenset({"raises", "keyboard"})


def self_declared_empty(value: str) -> bool:
    """True when a bullet's own value states its absence and the reason for it."""
    first_word = value.strip().split(",", 1)[0].strip().split(" ", 1)[0].lower()
    return first_word in {"none", "nothing"} and "because" in value.lower()


def states_no_claim(key: str, value: str) -> bool:
    """True when this bullet, on this key, mints no obligation because it says there is none."""
    return key in _SELF_DECLARABLE_EMPTY_KEYS and self_declared_empty(value)


def normative_claims(
    node_type: str, bullet_order: Iterable[Sequence[Any]]
) -> dict[tuple[str, int], str]:
    """Each claim's raw bullet value, keyed exactly as `attributed_checks` keys its checks."""
    excluded = set(condition_keys(node_type)) | set(address_keys(node_type))
    normative = set(normative_keys(node_type)) - excluded
    counts: dict[str, int] = {}
    claims: dict[tuple[str, int], str] = {}
    for row in bullet_order:
        key, value = str(row[0]), str(row[1])
        if key in normative:
            counts[key] = counts.get(key, 0) + 1
            if states_no_claim(key, value):
                continue
            claims[(key, counts[key])] = value
    return claims


CLAIM_COMBINERS: frozenset[str] = frozenset({"all", "branches"})


def claim_groups(
    node_type: str, bullet_order: Iterable[Sequence[Any]]
) -> dict[int, list[tuple[str, int]]]:
    """The claims each *authored* bullet mints, keyed by its position in the section."""
    normative = set(normative_keys(node_type))
    counts: dict[str, int] = {}
    groups: dict[int, list[tuple[str, int]]] = {}
    for row in bullet_order:
        key, bullet = str(row[0]), int(row[2])
        if key in normative:
            counts[key] = counts.get(key, 0) + 1
            groups.setdefault(bullet, []).append((key, counts[key]))
    return groups


def listed_checks(
    node_type: str, bullet_order: Iterable[Sequence[Any]]
) -> dict[tuple[str, int], list[str]]:
    """The checks each claim gets from a bullet beside its list, leaving out the checks nested under one child."""
    rows = list(bullet_order)
    normative = set(normative_keys(node_type))
    listed = {int(row[2]) for row in rows if str(row[0]) in normative}
    beside = [row for row in rows if str(row[0]) in normative or int(row[2]) not in listed]
    return _attributed(node_type, beside, {}, check_keys(node_type))[1]


def undetermined_claims(
    node_type: str,
    bullet_order: Iterable[Sequence[Any]],
    combiners: Mapping[int, str],
) -> dict[int, list[tuple[str, int]]]:
    """The nested claim lists whose children a check observes and whose combiner is unstated."""
    rows = list(bullet_order)
    groups = claim_groups(node_type, rows)
    fanned = listed_checks(node_type, rows)
    return {
        position: group
        for position, group in groups.items()
        if len(group) > 1
        and not combiners.get(position)
        and any(fanned.get(claim) for claim in group)
    }


def _attributed(
    node_type: str,
    bullet_order: Iterable[Sequence[Any]],
    combiners: Mapping[int, str],
    keys: Sequence[str],
) -> tuple[list[str], dict[tuple[str, int], list[str]]]:
    """Bind each bullet in *keys* to the nearest normative bullet above it, in document order.

    A bullet nested under one child of a claim list binds to that child alone, whatever the list's combiner.
    """
    contract, per_bullet = _attributed_indexed(node_type, bullet_order, combiners, keys)
    return (
        [value for _, value in contract],
        {claim: [value for _, value in values] for claim, values in per_bullet.items()},
    )


def _attributed_indexed(
    node_type: str,
    bullet_order: Iterable[Sequence[Any]],
    combiners: Mapping[int, str],
    keys: Sequence[str],
) -> tuple[list[tuple[int, str]], dict[tuple[str, int], list[tuple[int, str]]]]:
    """`_attributed`'s engine: the same walk, keeping each value's own authored per-key index."""
    normative = set(normative_keys(node_type))
    observing = set(keys)
    contract: list[tuple[int, str]] = []
    per_bullet: dict[tuple[str, int], list[tuple[int, str]]] = {}
    counts: dict[str, int] = {}
    observed_counts: dict[str, int] = {}
    owner: list[tuple[str, int]] = []
    authored = -1
    for row in bullet_order:
        key, value, bullet = str(row[0]), str(row[1]), int(row[2])
        if key in normative:
            counts[key] = counts.get(key, 0) + 1
            if bullet != authored:
                owner, authored = [], bullet
            owner.append((key, counts[key]))
        elif key in observing:
            observed_counts[key] = observed_counts.get(key, 0) + 1
            index = observed_counts[key]
            if not owner:
                contract.append((index, value))
            if bullet == authored:
                per_bullet.setdefault(owner[-1], []).append((index, value))
                continue
            if combiners.get(authored) == "branches":
                continue
            for target in owner:
                per_bullet.setdefault(target, []).append((index, value))
    return contract, per_bullet


UI_TYPES: tuple[UINodeType, ...] = (
    UINodeType(name="entries", kind="file", context=""),
    UINodeType(
        name="screen", kind="file", context="gui/screens",
        bullet_keys=(
            BulletKey("route", required=True, locator=True, address=True, value_kind="route"),
            BulletKey("requires", required=True, nested=True, link=True),
            BulletKey("params", required=True, nested=True, link=True, locator=True),
            BulletKey("entry", locator=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
        ),
    ),
    UINodeType(
        name="cli", kind="file", context="",
        required_sections=(SectionSpec("Commands", filled=True),),
        bullet_keys=(
            BulletKey("binary"),
            BulletKey("code", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
        ),
    ),
    UINodeType(
        name="server", kind="file", context="http",
        required_sections=(SectionSpec("Endpoints", filled=True),),
        bullet_keys=(
            BulletKey("code", link=True, owns=True),
            BulletKey("openapi", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("launch"),
            BulletKey("entry-url", value_kind="url"),
            BulletKey("health-path"),
            BulletKey("working-directory"),
            BulletKey("identity"),
            BulletKey("stop"),
            BulletKey("boot-timeout"),
        ),
    ),
    UINodeType(
        name="concept", kind="file", context="concepts",
        bullet_keys=(
            BulletKey("code", link=True, owns=True),
            BulletKey("extends", link=True),
            BulletKey("same-as", link=True),
            BulletKey("rule"),
            BulletKey("prefers", link=True),
            BulletKey("deprecates", link=True),
            BulletKey("verify", check=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="format", kind="file", context="formats",
        bullet_keys=(
            BulletKey("file", owns=True),
            BulletKey("config", owns=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="flow", kind="file", context="flows",
        bullet_keys=(
            BulletKey("start", normative=True, address=True),
            BulletKey("steps", nested=True, link=True),
            BulletKey("end", normative=True, address=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="runbook", kind="file", context="ops",
        required_sections=(SectionSpec("Steps", filled=True),),
        bullet_keys=(
            BulletKey("driver", required=True),
            BulletKey("environment", link=True),
            BulletKey("cli", link=True),
            BulletKey("surfaces", link=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("verify", check=True),
            BulletKey("entry-url", value_kind="url"),
            BulletKey("health-path"),
            BulletKey("identity"),
            BulletKey("bundle-id"),
            BulletKey("launch-screen", link=True),
            BulletKey("reuse"),
            BulletKey("fresh"),
            BulletKey("boot-timeout"),
            BulletKey("health-timeout"),
            BulletKey("stop"),
            BulletKey("working-directory"),
            BulletKey("secrets", nested=True),
        ),
    ),
    UINodeType(
        name="environment", kind="file", context="ops",
        bullet_keys=(
            BulletKey("selector"),
            BulletKey("services", nested=True),
            BulletKey("backing", nested=True),
            BulletKey("local-only"),
            BulletKey("code", link=True, owns=True),
            BulletKey("config", owns=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("capture", capture=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="component", kind="section", heading="Components",
        bullet_keys=(
            BulletKey("selector", locator=True, value_kind="selector"),
            BulletKey("role", required=True, normative=True, locator=True, address=True),
            BulletKey("one-per"),
            BulletKey("variants"),
            BulletKey("name", required=True, normative=True, locator=True, address=True),
            BulletKey("unique-by"),
            BulletKey("placement"),
            BulletKey("keyboard", normative=True, locator=True),
            BulletKey("extends", link=True),
            BulletKey("same-as", link=True),
            BulletKey("parent", link=True),
            BulletKey("exclusive-with", link=True, locator=True),
            BulletKey("states", normative=True, locator=True, condition=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="command", kind="section", heading="Commands",
        bullet_keys=(
            BulletKey("usage"),
            BulletKey("parent", link=True),
            BulletKey("flags", nested=True, entries=True),
            BulletKey("args"),
            BulletKey("does", nested=True, normative=True, locator=True),
            BulletKey("errors", normative=True, refusal=True),
            BulletKey("exits", normative=True),
            BulletKey("run", performs=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("capture", capture=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="endpoint", kind="section", heading="Endpoints",
        bullet_keys=(
            BulletKey("method", locator=True, address=True, value_kind="http-method"),
            BulletKey("path", locator=True, address=True, value_kind="route"),
            BulletKey("channel", locator=True, address=True),
            BulletKey("message", nested=True, entries=True, normative=True),
            BulletKey("does", nested=True, normative=True, locator=True),
            BulletKey("emits"),
            BulletKey("consumes"),
            BulletKey("response", nested=True, record=True,
                      properties=("media", "body", "notes", "field")),
            BulletKey("status", normative=True),
            BulletKey("errors", normative=True, refusal=True),
            BulletKey("error", normative=True, alias=True, refusal=True),
            BulletKey("auth", normative=True),
            BulletKey("authorization", normative=True, alias=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("openapi", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("arrange", performs=True),
            BulletKey("capture", capture=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="interaction", kind="section", heading="Interactions",
        bullet_keys=(
            BulletKey("on", required=True, link=True, locator=True),
            BulletKey("trigger", required=True, locator=True),
            BulletKey("role", required=True, locator=True),
            BulletKey("one-per"),
            BulletKey("variants"),
            BulletKey("name", required=True, locator=True),
            BulletKey("unique-by"),
            BulletKey("keyboard", required=True, normative=True, locator=True),
            BulletKey("when", normative=True, locator=True, condition=True),
            BulletKey("exclusive-with", link=True, locator=True),
            BulletKey("extends", link=True),
            BulletKey("same-as", link=True),
            BulletKey("does", required=True, nested=True, normative=True, locator=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("arrange", performs=True),
            BulletKey("capture", capture=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="invocation", kind="section", heading="Invocations",
        bullet_keys=(
            BulletKey("on", required=True, link=True, locator=True),
            BulletKey("trigger", required=True, locator=True),
            BulletKey("when", normative=True, locator=True, condition=True),
            BulletKey("extends", link=True),
            BulletKey("same-as", link=True),
            BulletKey("does", required=True, nested=True, normative=True, locator=True),
            BulletKey("emits"),
            BulletKey("consumes"),
            BulletKey("status", normative=True),
            BulletKey("errors", normative=True, refusal=True),
            BulletKey("error", normative=True, alias=True, refusal=True),
            BulletKey("auth", normative=True),
            BulletKey("authorization", normative=True, alias=True),
            BulletKey("run", performs=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("capture", capture=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="method", kind="section", heading="Methods", literal_id=True,
        bullet_keys=(
            BulletKey("sig"),
            BulletKey("abstract"),
            BulletKey("does", normative=True, locator=True),
            BulletKey("raises", normative=True),
            BulletKey("returns", normative=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("detail", link=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("capture", capture=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="field", kind="section", heading="Fields", literal_id=True,
        bullet_keys=(
            BulletKey("type"),
            BulletKey("default", normative=True),
            BulletKey("required", normative=True),
            BulletKey("semantics", normative=True),
            BulletKey("run", performs=True),
            BulletKey("code", link=True, owns=True),
            BulletKey("verify", check=True),
            BulletKey("fixture", arrange=True),
            BulletKey("capture", capture=True),
            BulletKey("tests", link=True),
        ),
    ),
    UINodeType(
        name="step", kind="section", heading="Steps",
        bullet_keys=(
            BulletKey("kind", required=True),
            BulletKey("run"),
            BulletKey("working-directory"),
            BulletKey("timeout"),
            BulletKey("env", nested=True),
            BulletKey("health"),
            BulletKey("produces"),
            BulletKey("verify", link=True),
            BulletKey("optional"),
            BulletKey("depends-on"),
        ),
    ),
    UINodeType(
        name="fixture", kind="file", context="fixtures",
        required_sections=(SectionSpec("Steps", filled=True),),
        bullet_keys=(
            BulletKey("args"),
            BulletKey("provides", nested=True, entries=True,
                      properties=("from", "read", "is")),
            BulletKey("needs", nested=True, link=True),
            BulletKey("verify", check=True),
            BulletKey("secrets", nested=True),
        ),
    ),
    UINodeType(name="untyped", kind="section"),
)

UI_TYPES_BY_NAME: dict[str, UINodeType] = {t.name: t for t in UI_TYPES}
NORMATIVE_KEYS_BY_TYPE: dict[str, tuple[str, ...]] = {
    t.name: tuple(b.key for b in t.bullet_keys if b.normative)
    for t in UI_TYPES if any(b.normative for b in t.bullet_keys)}
LOCATOR_KEYS: frozenset[str] = frozenset(b.key for t in UI_TYPES for b in t.bullet_keys if b.locator)
CONDITION_KEYS: frozenset[str] = frozenset(
    b.key for t in UI_TYPES for b in t.bullet_keys if b.condition)
ADDRESS_KEYS: frozenset[str] = frozenset(
    b.key for t in UI_TYPES for b in t.bullet_keys if b.address)
LOAD_BEARING_KEYS: frozenset[str] = frozenset(
    b.key for t in UI_TYPES for b in t.bullet_keys
    if b.normative or b.check or b.link or b.arrange or b.performs or b.locator
) - (frozenset(RELATION_KEYS) - LOCATOR_KEYS)
UI_HEADING_TO_TYPE: dict[str, str] = {
    t.heading: t.name for t in UI_TYPES if t.kind == "section" and t.heading}
UI_SECTION_HEADINGS: frozenset[str] = frozenset(UI_HEADING_TO_TYPE)


def ui_type(name: str | None) -> UINodeType | None:
    """The ``UINodeType`` for a declared ``type:`` value (by its base), or None."""
    return UI_TYPES_BY_NAME.get(base_type(name) or "")


def ui_type_named(name: str) -> UINodeType:
    """The ``UINodeType`` for ``name``."""
    found = ui_type(name)
    if found is None:
        raise KeyError(f"no UI node type named {name!r}; declared: {sorted(UI_TYPES_BY_NAME)}")
    return found


def is_known_type(type_value: str | None) -> bool:
    """True when a declared ``type:`` is a recognized built-in (incl."""
    base = base_type(type_value)
    return bool(base) and (base in REGISTRY_BY_NAME or base in UI_TYPES_BY_NAME)


def doc_root_of(type_value: str | None) -> str | None:
    """The docRoots key a page declaring *type_value* belongs under, or None for an unknown type."""
    base = base_type(type_value)
    if not base:
        return None
    entity = REGISTRY_BY_NAME.get(base)
    if entity is not None:
        return entity.doc_root
    uitype = UI_TYPES_BY_NAME.get(base)
    return uitype.doc_root if uitype is not None else None


def type_of(frontmatter: dict | None) -> str | None:
    """The declared concept `type` (e.g."""
    if not frontmatter:
        return None
    t = frontmatter.get("type")
    return str(t) if t else None


def base_type(type_value: str | None) -> str | None:
    """The registry key for a declared type: 'spec.plan' → 'spec', 'epic' → 'epic'."""
    if not type_value:
        return None
    return type_value.split(".", 1)[0]


def spec_type_for(filename: str) -> str:
    """The `type` for a spec doc — ``spec.<stem>``: 'plan.md' → 'spec.plan', 'executive.md' → 'spec.executive', 'plan-go.md' → 'spec.plan-go', 'vet.md' → 'spec.vet'."""
    stem = Path(filename).stem.strip().lower()
    return f"spec.{stem}" if stem else "spec"


@dataclass
class SeedSpec:
    """Parsed representation lifted from a `### <seed-id>` block (used by the loader)."""
    id: str
    summary: str = ""
    status: str = DEFAULT_SEED_STATUS
    fields: dict = field(default_factory=dict)
