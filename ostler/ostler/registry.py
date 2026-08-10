"""The machine-readable type registry — the single source of truth for the knowledge format.

`SPEC.md` is the prose definition; this module is its executable form. The loader (`model.py`),
validator (`doctor.py`), retrieval (`query.py`), and mutation (`crud.py`) all consult it so the
layout, identities, required frontmatter, and the `epic.md` body grammar are defined in exactly one
place.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Seed lifecycle
# ---------------------------------------------------------------------------
SEED_STATUSES = ("backlog", "researched", "covered", "resolved", "dropped", "deferred")
INACTIVE_SEED_STATUS = {"resolved", "dropped", "deferred"}
DEFAULT_SEED_STATUS = "backlog"

# Which layer of the system a seed lands in. Closed on purpose: the author workflow decides
# whether a story needs a mockup by asking whether any covered seed is `frontend`, so a typo
# here silently skips a design turn. `crud.add_seed` rejects a token outside this tuple.
# The companion `services` axis is deliberately *not* closed — nothing branches on it yet, so
# validating it would only add a failure mode.
SEED_LAYERS = ("frontend", "backend", "infra")

# ---------------------------------------------------------------------------
# epic.md body grammar (parsed by markdown.py's Section/Bullet tree)
# ---------------------------------------------------------------------------
SEEDS_HEADING = "Seeds"        # `## Seeds`   → `### <seed-id>` subsections
STORIES_HEADING = "Stories"    # `## Stories` → `### <slug>` subsections

# Metadata-bullet keys recognized inside a `### <seed-id>` block. Anything else is kept as a raw
# field. The first paragraph after the bullets is the seed `summary`.
SEED_META_KEYS = (
    "status", "surface", "legacySurface", "backing", "prerequisites", "sourceBullet",
    "layers", "services",
)
# The two list-valued seed keys, comma-separated on the bullet.
SEED_LIST_META_KEYS = ("layers", "services")
# Metadata-bullet keys recognized inside a `### <slug>` story block. `covers`/`depends on` are the
# graph edges; the rest are plain fields.
STORY_COVERS_KEY = "covers"        # → seedItems
STORY_DEPENDS_KEY = "depends on"   # → dependencies
STORY_META_KEYS = (STORY_COVERS_KEY, STORY_DEPENDS_KEY, "title", "id", "phase", "effort")

# A metadata value meaning "empty list" in covers/depends.
EMPTY_TOKENS = {"", "(none)", "none", "-", "—"}


# ---------------------------------------------------------------------------
# Document-body section contracts
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SectionSpec:
    """One required ``## Heading`` in a document body.

    *filled* separates the two questions a scaffolded document makes distinct: the heading
    exists (the scaffolder wrote it) versus somebody has since written under it. Only the
    second one means the document says anything.
    """
    heading: str
    filled: bool = False       # True → the heading must carry prose, not merely exist


# story.md's body contract. `crud.create_story` scaffolds *from this table* and `model` /
# `doctor` check against it, so the scaffold cannot drift into satisfying its own checkers —
# the exact failure that let 44 empty stories read as authored.
STORY_SECTIONS: tuple[SectionSpec, ...] = (
    SectionSpec("Context", filled=True),
    SectionSpec("Acceptance Criteria", filled=True),
    SectionSpec("Implementation Status", filled=False),   # scaffolded: holds the Status bullet
)

STORY_STATUS_HEADING = "Implementation Status"
STORY_STATUS_LABEL = "Status"          # `- **Status**: <value>` under the heading above
DEFAULT_STORY_STATUS = "Not started"

# OKF reserved per-bundle filenames.
RESERVED_FILES = {"index.md", "log.md"}


# ---------------------------------------------------------------------------
# Epic directory naming — `NNNN-<slug>`
# ---------------------------------------------------------------------------
# An epic's directory carries the order it was created in, so a listing of `docs/epics`
# reads as the work order rather than as an alphabetized set. The number is *not* an
# identity — identities are ostler-minted ids, which never change — so nothing is ever
# resolved by it: `0007-checkout-flow` and the bare `checkout-flow` name the same epic
# everywhere a name is taken. That tolerance is what keeps epics created before the
# numbering, hand-written `index.md` lines, and prompts that only know the slug valid.
EPIC_SEQ_WIDTH = 4
# Four digits minimum, so a slug that merely starts with a short number (`3d-preview`) is
# not read as a sequence prefix.
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
    """The number the next epic directory takes: one past the highest currently on disk.

    Derived, not persisted — there is no counter to keep in sync, and a clone or a merge
    computes the same answer from the same tree. The consequence is that deleting the last
    epic frees its number: `0003-` is handed out again once `0003-checkout` is gone. That is
    tolerable precisely because the number is *not* an identity — identity is the minted id,
    which is never reused — so the worst case is that two epics occupied the same rank at
    different times. Gaps in the middle are left alone: survivors are never renumbered, which
    would invalidate every path already written into a plan, a branch or a link.
    """
    taken = [n for n in (epic_seq(x) for x in names) if n is not None]
    return max(taken, default=0) + 1


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
    doc_root: str                      # one of: epics, milestones, features, specs
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
    required_sections: tuple[SectionSpec, ...] = ()   # file types: headings the body must carry
    bullet_keys: tuple[BulletKey, ...] = ()     # recognized keys, in canonical order
    body_template: str = ""                     # optional explicit skeleton override (scaffold)
    literal_id: bool = False                    # section types: `### id` is a code identifier
                                                 # (case-sensitive), not an author-chosen slug —
                                                 # `ostler fmt` must not kebab/lowercase it

    @property
    def bullet_by_key(self) -> dict[str, BulletKey]:
        return {b.key: b for b in self.bullet_keys}


# Bullet keys whose value is a code reference (``path::symbol`` / a test id), grounded against the
# repo at a *later* QA gate (profile §7.2), not at author time like doc links.
CODE_GROUNDING_KEYS = frozenset({"code", "verify"})
# Bullet keys naming an inter-node relation the linter resolves at author time. ``environment`` /
# ``cli`` / ``surfaces`` are the runbook profile's relations (docs/okf-runbook.md §4.1).
RELATION_KEYS = ("on", "parent", "extends", "steps", "presents", "detail",
                 "environment", "cli", "surfaces", "requires", "params", "leads-to",
                 "exclusive-with")


UI_TYPES: tuple[UINodeType, ...] = (
    # ---- file-level surfaces / nouns / artifacts ----
    UINodeType(
        name="screen", kind="file", context="gui/screens",
        bullet_keys=(
            # All three are required even when empty. A screen that simply omits `requires:` is
            # indistinguishable from one that is genuinely unconditional, and a walk cannot tell
            # "nothing to satisfy" from "nobody wrote it down" — so `none` must be *stated*.
            BulletKey("route", required=True),
            BulletKey("requires", required=True, nested=True, link=True),
            BulletKey("params", required=True, nested=True, link=True),
            # Optional, and a claim when present: this screen is entered from outside in-app
            # navigation (app root, emailed deep link, OAuth callback) and the value says how.
            # It exempts the screen from the reachability check, so it is not a silencer.
            BulletKey("entry"),
        ),
    ),
    UINodeType(
        name="cli", kind="file", context="",
        required_sections=(SectionSpec("Commands"),),
        bullet_keys=(BulletKey("binary"), BulletKey("code", link=True)),
    ),
    UINodeType(
        name="server", kind="file", context="http",
        required_sections=(SectionSpec("Endpoints"),),
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
        required_sections=(SectionSpec("Steps"),),
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
            # Required, because they are the same fact twice: the accessibility contract a screen
            # reader announces, and the `getByRole(role, {name})` a test locates by. `none` is a
            # legitimate value — a decorative or purely presentational element has no accessible
            # name — but it has to be *stated*, so "no name" and "nobody looked" stay distinguishable.
            BulletKey("role", required=True),
            BulletKey("name", required=True),
            BulletKey("keyboard"),   # how it's reached/operated by keyboard
            BulletKey("extends", link=True),
            BulletKey("parent", link=True),
            # Sibling(s) this control can never be in the DOM at the same time as. It is the runtime
            # fact a static role+name check cannot see: two controls that share a locator but never
            # co-render are not ambiguous. A *claim*, grounded in source (mutually-exclusive states,
            # variant switch) — not a way to silence a real same-screen collision.
            BulletKey("exclusive-with", link=True),
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
            # An interaction is by definition operable, so all three are required: the role/name
            # give `getByRole(role, {name})` instead of a brittle selector, and `keyboard:` records
            # how it is fired without a pointer. `none` on `keyboard:` is a claim that the control
            # is pointer-only — which is an accessibility defect worth being able to *find*, not a
            # blank to leave empty.
            BulletKey("role", required=True),
            BulletKey("name", required=True),
            BulletKey("keyboard", required=True),
            BulletKey("when"),
            BulletKey("exclusive-with", link=True),
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
    # A callable on a concept/format — a nested `### method: …` or a `## Methods` child. The id is
    # the literal method name (a code identifier), so `literal_id` keeps its case as authored.
    UINodeType(
        name="method", kind="section", heading="Methods", literal_id=True,
        bullet_keys=(
            BulletKey("sig"),
            BulletKey("abstract"),
            BulletKey("raises"),
            BulletKey("returns"),
            BulletKey("code", link=True),
            BulletKey("verify", link=True),
        ),
    ),
    # A typed attribute — a nested `### field: …` or a `## Fields` child. The id is the literal
    # field/property name (e.g. a JSON key or exported symbol) — often camelCase/PascalCase, so
    # `literal_id` keeps its case as authored instead of being lowercased into a slug.
    UINodeType(
        name="field", kind="section", heading="Fields", literal_id=True,
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


def ui_type_named(name: str) -> UINodeType:
    """The ``UINodeType`` for ``name``. ``KeyError`` if the registry declares none.

    The non-optional counterpart to `ui_type`, for the callers holding a name the registry
    itself produced — a `UI_HEADING_TO_TYPE` value, or a `type:` already accepted by
    `is_known_type`. They are not asking whether the type exists, and reaching through
    `ui_type` made a registry that lost an entry surface as ``AttributeError: 'NoneType'``
    somewhere downstream instead of naming what was missing. Use `ui_type` where absence is
    an answer rather than a bug.
    """
    found = ui_type(name)
    if found is None:
        raise KeyError(f"no UI node type named {name!r}; declared: {sorted(UI_TYPES_BY_NAME)}")
    return found


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


def spec_type_for(filename: str) -> str:
    """The `type` for a spec doc — ``spec.<stem>``: 'plan.md' → 'spec.plan', 'executive.md' →
    'spec.executive', 'plan-go.md' → 'spec.plan-go', 'vet.md' → 'spec.vet'.

    The subtype is descriptive, not dispatched on: nothing reads past ``base_type()``, and the
    spec EntityType requires only a non-empty ``type`` (no schema). So the stem is carried through
    verbatim rather than collapsed into a fixed vocabulary — that keeps a doc's kind queryable and
    matches the types already on disk (``spec.vet`` is what ``ostler vet`` writes).

    A doc with no stem to speak of falls back to the bare ``spec`` base type, which still conforms.
    """
    stem = Path(filename).stem.strip().lower()
    return f"spec.{stem}" if stem else "spec"


@dataclass
class SeedSpec:
    """Parsed representation lifted from a `### <seed-id>` block (used by the loader)."""
    id: str
    summary: str = ""
    status: str = DEFAULT_SEED_STATUS
    fields: dict = field(default_factory=dict)
