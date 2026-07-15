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


# ---------------------------------------------------------------------------
# OKF UI profile — the eleven UI/concept node types (see docs/okf-ui-profile.md)
# ---------------------------------------------------------------------------
# These are *built-in* types (not template kinds): first-class, recognized by the loader,
# navigation, and linter. They live under the ``features`` doc_root as ordinary OKF Concepts
# (``type:`` frontmatter for file-level nodes; ``### id`` under a typed ``## Heading`` for
# section-level ones). Each carries no bundled JSON Schema — conformance is the one hard OKF rule
# plus this profile's structural checks (``doctor.py``). One ``UINodeType`` per type is the single
# source of truth for the formatter (bullet order), the linter (required/link), and the scaffolder
# (skeleton).
@dataclass(frozen=True)
class BulletKey:
    """One recognized metadata bullet inside a UI node (``- key: value``)."""
    key: str
    required: bool = False
    nested: bool = False   # ``does:`` — value is a nested-bullet list, one child per effect
    link: bool = False     # value is a reference ostler resolves (doc link, or a code ref)


@dataclass(frozen=True)
class UINodeType:
    """One UI-profile node type. Generalizes ``SEED_META_KEYS`` / ``SEEDS_HEADING`` to any type."""
    name: str
    kind: str                                   # "file" | "section"
    heading: str = ""                           # section types: parent ``## Heading`` (e.g. "Interactions")
    context: str = ""                           # file types: context folder for scaffold placement
    required_sections: tuple[str, ...] = ()     # file types: headings that must be present
    bullet_keys: tuple[BulletKey, ...] = ()     # recognized keys, in canonical order
    body_template: str = ""                     # optional explicit skeleton override (scaffold)

    @property
    def bullet_by_key(self) -> dict[str, BulletKey]:
        return {b.key: b for b in self.bullet_keys}


# Bullet keys whose value is a code reference (``path::symbol`` / a test id), grounded against the
# repo at a *later* QA gate (profile §7.2), not at author time like doc links.
CODE_GROUNDING_KEYS = frozenset({"code", "verify"})
# Bullet keys naming an inter-node relation the linter resolves at author time. ``environment`` /
# ``cli`` / ``surfaces`` are the runbook profile's relations (docs/okf-runbook.md §4.1).
RELATION_KEYS = ("on", "parent", "extends", "steps", "presents", "detail",
                 "environment", "cli", "surfaces")


UI_TYPES: tuple[UINodeType, ...] = (
    # ---- file-level surfaces / nouns / artifacts ----
    UINodeType(
        name="screen", kind="file", context="gui/screens",
    ),
    UINodeType(
        name="cli", kind="file", context="",
        required_sections=("Commands",),
        bullet_keys=(BulletKey("binary"), BulletKey("code", link=True)),
    ),
    UINodeType(
        name="server", kind="file", context="http",
        required_sections=("Endpoints",),
        bullet_keys=(BulletKey("code", link=True), BulletKey("openapi", link=True)),
    ),
    UINodeType(
        name="concept", kind="file", context="concepts",
        bullet_keys=(BulletKey("code", link=True), BulletKey("extends", link=True)),
    ),
    UINodeType(
        name="format", kind="file", context="",
        bullet_keys=(BulletKey("file"), BulletKey("code", link=True)),
    ),
    UINodeType(
        name="flow", kind="file", context="flows",
        bullet_keys=(
            BulletKey("start"),
            BulletKey("steps", nested=True, link=True),
            BulletKey("end"),
            BulletKey("verify", link=True),
        ),
    ),
    # ---- operational surface: how the system is run/observed (docs/okf-runbook.md) ----
    UINodeType(
        name="runbook", kind="file", context="ops",
        required_sections=("Steps",),
        bullet_keys=(
            BulletKey("driver", required=True),   # web|mobile|http|cli|artifact|iac|none (§4.1)
            BulletKey("environment", link=True),  # the `environment` node this boots (default local)
            BulletKey("cli", link=True),          # the dev-CLI `cli` node it drives with
            BulletKey("surfaces", link=True),     # screen/server/cli/format nodes it exposes
            BulletKey("code", link=True),         # launch entry point `path::symbol`
        ),
    ),
    UINodeType(
        name="environment", kind="file", context="ops",
        bullet_keys=(
            BulletKey("selector"),                # how this environment is chosen
            BulletKey("services", nested=True),   # one child per service: its env-scoped URL/host
            BulletKey("backing", nested=True),    # backing projects/DBs/buckets/emulators
            BulletKey("local-only"),              # `true` → tooling must refuse without an override
        ),
    ),
    # ---- section-level elements / behaviors (a `### id` under a typed `## Heading`) ----
    UINodeType(
        name="component", kind="section", heading="Components",
        bullet_keys=(
            BulletKey("selector"),
            BulletKey("role"),       # ARIA/semantic role — the accessibility contract + robust
            BulletKey("name"),       # accessible name — Playwright `getByRole(role, {name})`
            BulletKey("keyboard"),   # how it's reached/operated by keyboard
            BulletKey("extends", link=True),
            BulletKey("parent", link=True),
            BulletKey("states"),
            BulletKey("code", link=True),
        ),
    ),
    UINodeType(
        name="command", kind="section", heading="Commands",
        bullet_keys=(
            BulletKey("usage"),
            BulletKey("parent", link=True),
            BulletKey("flags"),
            BulletKey("args"),
            BulletKey("does", nested=True),
            BulletKey("code", link=True),
            BulletKey("detail", link=True),
        ),
    ),
    UINodeType(
        name="endpoint", kind="section", heading="Endpoints",
        bullet_keys=(
            BulletKey("method"),
            BulletKey("path"),
            BulletKey("channel"),
            BulletKey("message"),
            BulletKey("does", nested=True),
            BulletKey("emits"),
            BulletKey("consumes"),
            BulletKey("code", link=True),
            BulletKey("openapi", link=True),
            BulletKey("detail", link=True),
        ),
    ),
    UINodeType(
        name="interaction", kind="section", heading="Interactions",
        bullet_keys=(
            BulletKey("on", required=True, link=True),
            BulletKey("trigger", required=True),
            BulletKey("role"),       # role/name of the target — the robust locator basis…
            BulletKey("name"),       # …`getByRole(role, {name})` instead of a brittle selector
            BulletKey("keyboard"),   # key/shortcut that fires it (e.g. `⌘K`)
            BulletKey("when"),
            BulletKey("does", required=True, nested=True),
            BulletKey("code", link=True),
            BulletKey("verify", link=True),
        ),
    ),
    UINodeType(
        name="invocation", kind="section", heading="Invocations",
        bullet_keys=(
            BulletKey("on", required=True, link=True),
            BulletKey("trigger", required=True),
            BulletKey("when"),
            BulletKey("does", required=True, nested=True),
            BulletKey("emits"),
            BulletKey("consumes"),
            BulletKey("code", link=True),
            BulletKey("verify", link=True),
        ),
    ),
    # A callable on a concept/format — a nested `### method: …` or a `## Methods` child.
    UINodeType(
        name="method", kind="section", heading="Methods",
        bullet_keys=(
            BulletKey("sig"),
            BulletKey("abstract"),
            BulletKey("raises"),
            BulletKey("returns"),
            BulletKey("code", link=True),
            BulletKey("verify", link=True),
        ),
    ),
    # A typed attribute — a nested `### field: …` or a `## Fields` child.
    UINodeType(
        name="field", kind="section", heading="Fields",
        bullet_keys=(
            BulletKey("type"),
            BulletKey("default"),
            BulletKey("required"),
            BulletKey("semantics"),
        ),
    ),
    # One ordered boot step of a `runbook` — a `### id` under its `## Steps` (docs/okf-runbook.md §4.3).
    UINodeType(
        name="step", kind="section", heading="Steps",
        bullet_keys=(
            BulletKey("kind", required=True),   # prepare|service|seed|run|health|verify|drive
            BulletKey("run"),                   # the exact bounded command
            BulletKey("working-directory"),     # cwd, when not the repo root
            BulletKey("env", nested=True),      # env-var wiring this step needs
            BulletKey("health"),                # service/health steps: the real readiness signal
            BulletKey("produces"),              # run steps: output artifact path(s)/glob(s)
            BulletKey("verify", link=True),     # run/verify steps: golden/deterministic/test-id
            BulletKey("optional"),              # `true` for best-effort steps
            BulletKey("depends-on"),            # ordering hint (default: document order)
            BulletKey("provenance"),            # derived (build pass) | verified (walkthrough)
        ),
    ),
    # A heading that names no type — promoted anyway so every section is a node (its links are
    # captured, it nests, it's queryable) without inventing a garbage type from prose.
    UINodeType(name="untyped", kind="section"),
)

UI_TYPES_BY_NAME: dict[str, UINodeType] = {t.name: t for t in UI_TYPES}
# ``## Heading`` → the section-node type it contains (profile §4's implicit-type table).
UI_HEADING_TO_TYPE: dict[str, str] = {
    t.heading: t.name for t in UI_TYPES if t.kind == "section" and t.heading}
UI_SECTION_HEADINGS: frozenset[str] = frozenset(UI_HEADING_TO_TYPE)


def ui_type(name: str | None) -> UINodeType | None:
    """The ``UINodeType`` for a declared ``type:`` value (by its base), or None."""
    return UI_TYPES_BY_NAME.get(base_type(name) or "")


def is_known_type(type_value: str | None) -> bool:
    """True when a declared ``type:`` is a recognized built-in (incl. UI types)."""
    base = base_type(type_value)
    return bool(base) and (base in REGISTRY_BY_NAME or base in UI_TYPES_BY_NAME)


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
