"""The machine-readable type registry — the single source of truth for the knowledge format.

`SPEC.md` is the prose definition; this module is its executable form. The loader (`model.py`),
validator (`doctor.py`), retrieval (`query.py`), and mutation (`crud.py`) all consult it so the
layout, identities, required frontmatter, and the `epic.md` body grammar are defined in exactly one
place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Seed lifecycle
# ---------------------------------------------------------------------------
SEED_STATUSES = ("backlog", "researched", "covered", "resolved", "dropped", "deferred")
INACTIVE_SEED_STATUS = {"resolved", "dropped", "deferred"}
DEFAULT_SEED_STATUS = "backlog"

# ---------------------------------------------------------------------------
# epic.md body grammar (parsed by markdown.py's Section/Bullet tree)
# ---------------------------------------------------------------------------
SEEDS_HEADING = "Seeds"        # `## Seeds`   → `### <seed-id>` subsections
STORIES_HEADING = "Stories"    # `## Stories` → `### <slug>` subsections

# Metadata-bullet keys recognized inside a `### <seed-id>` block. Anything else is kept as a raw
# field. The first paragraph after the bullets is the seed `summary`.
SEED_META_KEYS = (
    "status", "surface", "legacySurface", "backing", "prerequisites", "sourceBullet",
)
# Metadata-bullet keys recognized inside a `### <slug>` story block. `covers`/`depends on` are the
# graph edges; the rest are plain fields.
STORY_COVERS_KEY = "covers"        # → seedItems
STORY_DEPENDS_KEY = "depends on"   # → dependencies
STORY_META_KEYS = (STORY_COVERS_KEY, STORY_DEPENDS_KEY, "title", "id", "phase", "effort")

# A metadata value meaning "empty list" in covers/depends.
EMPTY_TOKENS = {"", "(none)", "none", "-", "—"}

# OKF reserved per-bundle filenames.
RESERVED_FILES = {"index.md", "log.md"}


# ---------------------------------------------------------------------------
# Entity types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EntityType:
    """One Concept type in the knowledge format.

    *location* is a glob (``Path.glob`` style) **relative to the type's doc_root**, so config
    overrides of docRoots are honored (e.g. story → doc_root ``epics`` + location
    ``*/stories/*/story.md``).
    *doc_root* names the docRoots key the glob lives under (for config-overridable roots).
    *required* lists frontmatter keys that must be present and non-empty.
    *schema* is the bundled JSON Schema validated against the frontmatter (None = conformance only).
    """
    name: str
    doc_root: str                      # one of: epics, knowledge, features, specs
    location: str                      # glob relative to doc_root
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
        name="story", doc_root="epics", location="*/stories/*/story.md",
        required=("type", "slug", "status"), schema="story.schema.json",
        note="Leaf story spec. Edges (covers/depends) live in the epic's `## Stories` section.",
    ),
    EntityType(
        name="knowledge", doc_root="knowledge", location="**/*.md",
        required=("type", "surface"), schema="knowledge-record.schema.json",
        note="Surface knowledge record (markdown + frontmatter).",
    ),
    EntityType(
        name="feature", doc_root="features", location="**/*.md",
        required=("type", "slug", "title"), schema="feature.schema.json",
        note="Per-surface feature doc; the inventory is derived from these.",
    ),
    EntityType(
        name="spec", doc_root="specs", location="*/*.md",
        required=("type",), schema=None,
        note="Coder process artifact (spec.plan / spec.review / spec.qa). Conformance only.",
    ),
)

REGISTRY_BY_NAME: dict[str, EntityType] = {t.name: t for t in REGISTRY}


def type_of(frontmatter: dict | None) -> str | None:
    """The declared concept `type` (e.g. 'epic', 'spec.plan'), or None when absent/blank."""
    if not frontmatter:
        return None
    t = frontmatter.get("type")
    return str(t) if t else None


def base_type(type_value: str | None) -> str | None:
    """The registry key for a declared type: 'spec.plan' → 'spec', 'epic' → 'epic'."""
    if not type_value:
        return None
    return type_value.split(".", 1)[0]


@dataclass
class SeedSpec:
    """Parsed representation lifted from a `### <seed-id>` block (used by the loader)."""
    id: str
    summary: str = ""
    status: str = DEFAULT_SEED_STATUS
    fields: dict = field(default_factory=dict)
