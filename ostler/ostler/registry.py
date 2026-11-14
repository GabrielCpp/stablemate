"""The machine-readable type registry: the single source of truth for the planning types."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

SEED_STATUSES = ("backlog", "researched", "covered", "resolved", "dropped", "deferred")
INACTIVE_SEED_STATUS = {"resolved", "dropped", "deferred"}
DEFAULT_SEED_STATUS = "backlog"

SEED_LAYERS = ("frontend", "backend", "infra")
SEED_DESIGNS = ("required", "preserve")

SEEDS_HEADING = "Seeds"
STORIES_HEADING = "Stories"

SEED_META_KEYS = (
    "status", "surface", "legacySurface", "backing", "prerequisites", "sourceRecord",
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

MILESTONE_FILE = "milestone.md"
MILESTONE_STATUSES = ("proposed", "approved", "authored", "delivered", "superseded")
MILESTONE_DEFAULT_STATUS = "proposed"
MILESTONE_JOURNEYS_HEADING = "User Journeys"
MILESTONE_OPEN_DECISIONS_HEADING = "Open Decisions"
MILESTONE_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec("Outcome", filled=True),
    SectionSpec("Release Boundary", filled=True),
    SectionSpec(MILESTONE_JOURNEYS_HEADING, filled=True),
    SectionSpec("Architecture Decisions", filled=True),
    SectionSpec("Constraints", filled=True),
    SectionSpec("Acceptance", filled=True),
    SectionSpec("Non-Goals", filled=True),
)


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
    """One document type the planning graph reads."""
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
        name="milestone", doc_root="milestones", location=f"*/{MILESTONE_FILE}",
        required=("type", "title", "status"), schema="milestone.schema.json",
        note="Release contract: `docs/milestones/<slug>/milestone.md`, a dependency-ordered group of epics.",
    ),
    EntityType(
        name="story", doc_root="epics", location="*/stories/*/story.md",
        required=("type", "slug", "status"), schema="story.schema.json",
        note="Leaf story spec. Edges (covers/depends) live in the epic's `## Stories` section.",
    ),
    EntityType(
        name="spec", doc_root="specs", location="*/*.md",
        required=("type",), schema=None,
        note="Coder process artifact (spec.<stem>: spec.plan, spec.qa, …). Conformance only.",
    ),
)

REGISTRY_BY_NAME: dict[str, EntityType] = {t.name: t for t in REGISTRY}



def is_known_type(type_value: str | None) -> bool:
    """True when a declared ``type:`` is a recognized built-in (incl."""
    base = base_type(type_value)
    return bool(base) and base in REGISTRY_BY_NAME


def doc_root_of(type_value: str | None) -> str | None:
    """The doc-root key a page declaring *type_value* belongs under, or None for an unknown type."""
    base = base_type(type_value)
    if not base:
        return None
    entity = REGISTRY_BY_NAME.get(base)
    return entity.doc_root if entity is not None else None


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
