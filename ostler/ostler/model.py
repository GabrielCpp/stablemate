"""The unified organization model: load the typed knowledge graph from markdown Concepts.

Every entity is an OKF Concept (markdown + frontmatter); see ``SPEC.md`` and ``registry.py``. An
epic's seeds and story dependency-DAG are folded into its ``epic.md`` body (``## Seeds`` /
``## Stories``) and read back with the hierarchical markdown parser — there are no ``seed.json`` /
``dependencies.json`` files.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from ostler import dynamic_registry, index, markdown, registry

# Seed statuses that no longer require story coverage.
INACTIVE_SEED_STATUS = registry.INACTIVE_SEED_STATUS


@dataclass
class SeedItem:
    id: str
    status: str
    summary: str = ""
    raw: dict = field(default_factory=dict)
    # Which layers of the system this seed touches (`registry.SEED_LAYERS`) and which services
    # it lands in. Both are arrays: one seed routinely spans a screen and the API behind it.
    # An empty `layers` means *unclassified*, not "touches nothing" — the author's mockup gate
    # reads it that way and keeps the design turn rather than skipping it on a missing tag.
    layers: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    # ``required`` changes a visual contract; ``preserve`` retains an existing one. Blank is
    # unclassified and therefore fail-closed by Author's mockup gate.
    design: str = ""

    @property
    def active(self) -> bool:
        return self.status not in INACTIVE_SEED_STATUS


@dataclass
class Story:
    slug: str
    title: str
    path: str
    # The seeds this story covers, from the epic's `## Stories` block.
    seed_items: list[str]
    # The sibling stories that must finish first, from *this story's* `## Dependencies` section —
    # so the blockers are visible in the file a reader has open. Empty until `_attach_story_md`
    # reads the story.md; a story whose file is missing has no blockers to state.
    dependencies: list[str]
    # Allocated id, repo-prefixed (e.g. "TODO-15"). Minted by ostler when the story is
    # created, recorded both in the epic's `## Stories` block and in the story's own
    # frontmatter — mirroring Epic.eid so a story is addressable by id, not only by slug.
    eid: str = ""
    # Provider-neutral tracker alias, owned by story.md rather than duplicated into epic.md.
    external_key: str = ""
    # The copy read from story.md, retained separately so doctor can detect disagreement with
    # the parent epic block instead of silently preferring one identity.
    file_eid: str = ""
    raw: dict = field(default_factory=dict)
    story_md: Path | None = None
    status: str = ""
    body_status: str = ""
    # Every in-repo document this story links to, verbatim as written (relative to story.md
    # or repo-relative). This is how a story cites the OKF book: a UI node's identity is a
    # repo-relative path (optionally `path#anchor`), so a citation is an ordinary link.
    # Resolution to a node is `Graph.resolve_doc_ref` + `Graph.find_ui_node`, not done here —
    # the raw href is kept so a *dangling* citation stays visible instead of vanishing.
    doc_refs: list[str] = field(default_factory=list)
    # Headings from `registry.STORY_SECTIONS` the story.md is missing or leaves empty. A freshly
    # scaffolded story has every `filled` one here — which is what distinguishes "the file exists"
    # from "somebody wrote the story".
    unwritten_sections: list[str] = field(default_factory=list)
    # The same headings, each carrying *why* — `"Dependencies (missing)"` against
    # `"Context (empty)"`. The two are not the same repair: an empty section is waiting on an
    # author, a missing one predates the contract that requires it and no amount of writing
    # under the headings that are there will satisfy the check.
    unwritten_detail: list[str] = field(default_factory=list)
    # Bullets under `## Dependencies` that do not state a blocker — see
    # `story_dependency_strays`. Non-empty means the section's shape is wrong, which is
    # indistinguishable from "no blockers" in `dependencies` alone.
    dependency_strays: list[str] = field(default_factory=list)
    # The declared QA fixtures this story's `## Fixtures` section says its plan arranges state
    # with, and the bullets under that heading that state something else. Same pair, and the
    # same reason, as `dependencies` / `dependency_strays` above.
    fixtures: list[str] = field(default_factory=list)
    fixture_strays: list[str] = field(default_factory=list)
    # Required sections this story places out of `registry.STORY_SECTIONS` order. Separate from
    # `unwritten_sections` because it is a different defect with a different repair: the story
    # says everything it must, in an order that makes two documents of the same contract read
    # differently. Kept here so `doctor` and the author's own validator ask one question.
    misordered_sections: list[str] = field(default_factory=list)

    @property
    def authored(self) -> bool:
        """Whether the story says anything: it has a story.md and honors the body contract.

        Orthogonal to :attr:`status` — that tracks *build* progress (Not started → QA passed),
        this tracks whether there is a spec to build from at all.
        """
        return self.story_md is not None and not self.unwritten_sections

    @property
    def aliases(self) -> tuple[str, ...]:
        """Every stable spelling accepted as this story, de-duplicated in precedence order."""
        return tuple(
            dict.fromkeys(
                value for value in (self.eid, self.external_key, self.slug) if value
            )
        )


@dataclass
class Epic:
    name: str
    directory: Path
    title: str = ""
    status: str = ""
    eid: str = ""                       # allocated id from frontmatter (e.g. "acme-15")
    epic_md: Path | None = None
    seeds: list[SeedItem] = field(default_factory=list)
    stories: list[Story] = field(default_factory=list)

    @property
    def seed_ids(self) -> set[str]:
        return {s.id for s in self.seeds}


@dataclass
class Milestone:
    name: str
    path: Path
    title: str = ""
    status: str = ""
    eid: str = ""
    depends_on: list[str] = field(default_factory=list)
    source_items: list[str] = field(default_factory=list)
    epics: list[str] = field(default_factory=list)


@dataclass
class FeatureRecord:
    slug: str
    area: str
    title: str
    path: Path
    data: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.area}/{self.slug}" if self.area else self.slug


@dataclass
class UINode:
    """A node of the OKF UI profile (docs/okf-ui-profile.md).

    Two shapes, both ordinary OKF content: a **file** node (identity = path; ``type:`` frontmatter
    sets it) or a **section** node (identity = ``path#anchor``; a ``### id`` under a typed
    ``## Heading`` — the heading implies the type). ``line`` is 1-based, file-absolute, for located
    findings and byte-precise edits.
    """
    type: str                   # "screen" | "interaction" | ...
    kind: str                   # "file" | "section"
    id: str                     # file: repo-relative path; section: "<repo-rel-path>#<anchor>"
    path: Path
    anchor: str = ""            # section nodes only
    title: str = ""
    line: int = 0               # 1-based, file-absolute (the file's H1 / the `### id` line)
    level: int = 0              # heading depth 1-6 (file node = 1); drives the hierarchy
    parent: str = ""            # id of the enclosing node (containment); "" for a file/root node
    meta: dict = field(default_factory=dict)                 # parsed `- key: value` bullets
    # The same bullets in document order, which `meta` cannot express: see `_bullet_pairs`.
    bullet_order: list[tuple[str, str, int]] = field(default_factory=list)
    links: list = field(default_factory=list)                # (text, href) inside the node's region
    data: dict = field(default_factory=dict)                 # frontmatter (file nodes)


@dataclass
class Graph:
    root: Path
    org_name: str
    profile: str  # "full" | "exploration"
    doc_roots: dict[str, Path]
    epics: list[Epic] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    features: list[FeatureRecord] = field(default_factory=list)
    ui_nodes: list[UINode] = field(default_factory=list)
    ids: dict | None = None
    template_kinds: tuple = ()

    # ---- UI-profile indexes --------------------------------------------------
    def ui_nodes_of_type(self, type_name: str) -> list[UINode]:
        return [n for n in self.ui_nodes if n.type == type_name]

    def find_ui_node(self, ident: str) -> UINode | None:
        """Look up a UI node by its identity (repo-relative path, or ``path#anchor``)."""
        for n in self.ui_nodes:
            if n.id == ident:
                return n
        return None

    def resolve_doc_ref(self, href: str, *, origin: Path | None = None) -> str:
        """Normalize a document link into a node identity (``<repo-rel-path>[#anchor]``).

        A UI node's identity is always repo-relative, but a link inside a doc is written
        however is convenient — relative to the citing file (``../../okf/web/login.md#submit``),
        root-anchored (``/docs/okf/web/login.md``), or the node id copied verbatim out of the
        book (``docs/okf/web/login.md``). All three name the same node, so all three resolve
        here: the origin-relative and repo-relative readings are both tried and whichever lands
        on a real file wins, with the origin-relative one preferred when both do (that is what
        the link syntax means) and used as the answer when neither does — a citation that
        resolves to nothing is *returned*, not dropped, so the caller can report it as dangling
        instead of confusing a typo'd node id with a document that was never cited.
        """
        raw = href.split("?", 1)[0]
        path_part, _, anchor = raw.partition("#")
        if not path_part:
            return ""

        candidates: list[str] = []
        if not path_part.startswith("/") and origin is not None:
            try:
                candidates.append(
                    (origin.parent / path_part).resolve()
                    .relative_to(self.root.resolve()).as_posix())
            except ValueError:  # escapes the repo — not a document in this repo
                pass
        candidates.append(path_part.lstrip("/"))

        rel = next((c for c in candidates if (self.root / c).is_file()), candidates[0])
        return f"{rel}#{anchor}" if anchor else rel

    # ---- indexes -------------------------------------------------------------
    def epic_of_seed(self, seed_id: str) -> Epic | None:
        for e in self.epics:
            if seed_id in e.seed_ids:
                return e
        return None

    def epic_of_story(self, slug: str) -> Epic | None:
        for e in self.epics:
            if any(s.slug == slug for s in e.stories):
                return e
        return None

    def all_story_slugs(self) -> set[str]:
        return {s.slug for e in self.epics for s in e.stories}

    def milestone_by_name(self, name: str) -> Milestone | None:
        for milestone in self.milestones:
            if name in (milestone.name, milestone.eid):
                return milestone
        return None

    def find_story(self, ref: str) -> tuple[Epic, Story] | None:
        """The story named by an id, external key, or slug.

        Ambiguity is an invalid graph rather than an ordering rule. Doctor reports the same
        collision mechanically, while direct API callers fail here instead of receiving whichever
        epic happened to load first.
        """
        matches = [
            (epic, story)
            for epic in self.epics
            for story in epic.stories
            if ref in story.aliases
        ]
        if len(matches) > 1:
            paths = ", ".join(story.path for _, story in matches)
            raise ValueError(f"story reference {ref!r} is ambiguous: {paths}")
        return matches[0] if matches else None


# ---------------------------------------------------------------------------
# epic.md body parsing  (## Seeds / ## Stories → SeedItem / Story)
# ---------------------------------------------------------------------------
def required_section_problems(
    doc: markdown.MarkdownDoc,
    specs: tuple[registry.SectionSpec, ...],
) -> list[tuple[registry.SectionSpec, str]]:
    """``(spec, "missing"|"empty")`` for every required section the body does not honor.

    The one implementation of the required-section rule: the story contract
    (``registry.STORY_SECTIONS``) and the UI profile's ``required_sections`` both check here,
    so a scaffolded heading can never satisfy a check that meant "written".
    """
    problems: list[tuple[registry.SectionSpec, str]] = []
    for spec in specs:
        section = doc.find_section(spec.heading)
        if section is None:
            problems.append((spec, "missing"))
        elif spec.filled and section.is_empty:
            problems.append((spec, "empty"))
    return problems


def section_order_problems(
    doc: markdown.MarkdownDoc,
    specs: tuple[registry.SectionSpec, ...],
) -> list[str]:
    """The required headings this body places out of the contract's order, as messages.

    Presence is not enough once two paths can add a missing section: a scaffolder inserting at
    a fixed offset and an author writing free-hand will both satisfy
    :func:`required_section_problems` while producing documents that read differently. Order is
    the part of the contract that makes those two paths one path, so it is checked here — in the
    same module, against the same table — rather than left to whichever caller remembers.

    Sections the contract does not name are ignored entirely: this orders the required ones
    relative to each other and says nothing about what a document adds around them.
    """
    present: list[tuple[str, int]] = []
    for spec in specs:
        section = doc.find_section(spec.heading)
        if section is not None:
            present.append((spec.heading, section.line_start))
    return [
        f"`## {heading}` must come after `## {earlier}`"
        for (earlier, earlier_line), (heading, line) in zip(present, present[1:])
        if line < earlier_line
    ]


def status_bullet(doc: markdown.MarkdownDoc) -> markdown.Bullet | None:
    """The ``- **Status**:`` field of a parsed story doc, or ``None``.

    Scoped to ``## Implementation Status`` when that heading exists, so the word "Status" in a
    story's own prose is never mistaken for the field.
    """
    section = doc.find_section(registry.STORY_STATUS_HEADING)
    if section is not None:
        return section.labelled(registry.STORY_STATUS_LABEL)
    return doc.find_bullet(registry.STORY_STATUS_LABEL)


def story_status(doc: markdown.MarkdownDoc) -> str:
    """A story's status: frontmatter ``status:`` first, else the parsed bullet (``""`` if neither).

    The one place that answers "what does this story.md say its status is" — the graph loader,
    ``crud.set_status`` and the workflow scripts all read it here, so a substring of the prose can
    never stand in for the field.
    """
    fm = doc.frontmatter or {}
    status = fm.get("status")
    if not status:
        bullet = status_bullet(doc)
        status = bullet.value if bullet else ""
    return str(status or "")


def story_body_status(doc: markdown.MarkdownDoc) -> str:
    """The visible ``- **Status**:`` value in the story body, or ``""`` when absent."""
    bullet = status_bullet(doc)
    return str(bullet.value if bullet else "" or "")


def _labelled_values(doc: markdown.MarkdownDoc, heading: str, label: str) -> list[str]:
    """The values of every ``- <label>: <value>`` bullet under ``## <heading>``, in order.

    Shared by the two list sections a story states in its own body — its blockers and its QA
    fixtures. Only labelled bullets carry an entry, so the section's ``(none)`` — and any prose
    somebody adds around the list — contributes nothing without the parser having to recognize
    the word.
    """
    section = doc.find_section(heading)
    if section is None:
        return []
    want = label.strip().lower()
    values: list[str] = []
    for top in section.bullets:
        for bullet in top.walk():
            if bullet.label != want:
                continue
            # A comma list on one bullet is tolerated: the canonical form is a bullet each, but
            # a hand edit that writes `- Blocked by: a, b` states the same graph.
            values += [value for value in _split_list(bullet.value) if value not in values]
    return values


def _labelled_strays(doc: markdown.MarkdownDoc, heading: str, label: str) -> list[str]:
    """Bullets under ``## <heading>`` stating something other than ``- <label>:``.

    A story.md is written by an agent, and the failure mode that costs the most is the quiet one:
    a rewrite that turns the list into prose or renames the label empties it without anything
    failing. :func:`_labelled_values` cannot tell that apart from a story with no entries, so the
    shape is reported separately and `doctor` turns it into an error.
    """
    section = doc.find_section(heading)
    if section is None:
        return []
    want = label.strip().lower()
    return [
        bullet.text.strip()
        for top in section.bullets
        for bullet in top.walk()
        if bullet.label != want
    ]


def story_dependencies(doc: markdown.MarkdownDoc) -> list[str]:
    """The sibling slugs a story's ``## Dependencies`` section says block it.

    The one place that answers "what does this story.md say blocks it".
    """
    return _labelled_values(doc, registry.STORY_DEPS_HEADING, registry.STORY_DEPS_LABEL)


def story_fixtures(doc: markdown.MarkdownDoc) -> list[str]:
    """The declared QA fixtures a story's ``## Fixtures`` section says its plan arranges with.

    The one place that answers "what does this story.md say it arranges". A name here is a
    claim in both directions — the repo declares it, and this story's own plan asks for it —
    and `doctor` is what holds it to both.
    """
    return _labelled_values(doc, registry.STORY_FIXTURES_HEADING, registry.STORY_FIXTURES_LABEL)


def story_fixture_strays(doc: markdown.MarkdownDoc) -> list[str]:
    """Bullets under ``## Fixtures`` that state something other than ``- Fixture:``."""
    return _labelled_strays(doc, registry.STORY_FIXTURES_HEADING, registry.STORY_FIXTURES_LABEL)


def story_dependency_strays(doc: markdown.MarkdownDoc) -> list[str]:
    """Bullets under ``## Dependencies`` that state something other than ``- Blocked by:``."""
    return _labelled_strays(doc, registry.STORY_DEPS_HEADING, registry.STORY_DEPS_LABEL)


def _bullet_pairs(section: markdown.Section) -> list[tuple[str, str, int]]:
    """Every `- key: value` of a section as ``(key, value, bullet)`` in document order.

    The same bullets :func:`_meta_from_bullets` folds into a dict, before the fold loses where
    they sat. Order across keys is the whole point: a book writes a claim and then the `verify:`
    that observes it, and that adjacency is the only place the binding between the two is
    written down. A bullet with nested children yields one pair per value, matching the flat
    list the dict stores, so a position in this sequence and an index into `meta[key]` count the
    same things — and the third element says which of them came from the *same* authored
    bullet, which the flat list can no longer tell: two sibling `- errors:` bullets and one
    `- errors:` with two children are indistinguishable once flattened, and they bind a
    following `verify:` differently.
    """
    pairs: list[tuple[str, str, int]] = []
    for position, bullet in enumerate(section.bullets):
        text = bullet.text.strip()
        if ":" not in text:
            continue
        key, _, value = text.partition(":")
        nested = [item.text.strip() for child in bullet.children for item in child.walk()]
        pairs.extend((key.strip().lower(), item, position)
                     for item in (value.strip(), *nested) if item)
    return pairs


def _meta_from_bullets(section: markdown.Section) -> dict[str, str | list[str]]:
    """Parse the leading `- key: value` metadata bullets of a section into an ordered dict.

    Keys are lowercased; the first ``:`` separates key and value (so ``blocked by: a, b`` keeps the
    spaced key). Bullets without a ``:`` are ignored.
    """
    meta: dict[str, str | list[str]] = {}
    for bullet in section.bullets:
        text = bullet.text.strip()
        if ":" not in text:
            continue
        key, _, value = text.partition(":")
        key = key.strip().lower()
        value = value.strip()
        nested = [item.text.strip() for child in bullet.children for item in child.walk()]
        values = [item for item in (value, *nested) if item]
        parsed: str | list[str] = "" if not values else values[0] if len(values) == 1 else values
        previous = meta.get(key)
        if previous is None:
            meta[key] = parsed
        elif isinstance(previous, list):
            previous.extend(values)
        else:
            meta[key] = [previous, *values]
    return meta


def _meta_scalar(meta: dict[str, str | list[str]], key: str, default: str = "") -> str:
    value = meta.get(key, default)
    return value[0] if isinstance(value, list) and value else str(value)


def _first_paragraph(section: markdown.Section) -> str:
    """The first prose paragraph after the section's metadata bullets (the seed summary)."""
    lines = section.body_lines
    start = section.line_start + 1
    if section.bullets:
        start = max(b.line_end for b in section.bullets)
    para: list[str] = []
    for ln in lines[start:section.line_end]:
        if ln.strip():
            para.append(ln.strip())
        elif para:
            break
    return " ".join(para)


def _split_list(value: str) -> list[str]:
    """Parse a `covers:`/`Blocked by:` value into a list, honoring the empty tokens."""
    if value.strip().lower() in registry.EMPTY_TOKENS:
        return []
    return [p.strip() for p in value.split(",") if p.strip()
            and p.strip().lower() not in registry.EMPTY_TOKENS]


def _meta_tags(meta: dict[str, str | list[str]], key: str) -> tuple[str, ...]:
    """A list-valued seed meta key as normalized tags, from either spelling.

    `- layers: frontend, backend` and a nested bullet list under `- layers:` both reach here —
    :func:`_meta_from_bullets` yields a string for the first and a list for the second — so
    flatten either into the same tuple. Tags are lowercased and de-duplicated in order.
    """
    value = meta.get(key, "")
    parts = value if isinstance(value, list) else [value]
    tags: list[str] = []
    for part in parts:
        for tag in _split_list(str(part)):
            lowered = tag.lower()
            if lowered not in tags:
                tags.append(lowered)
    return tuple(tags)


def _parse_seeds(doc: markdown.MarkdownDoc) -> list[SeedItem]:
    section = doc.find_section(registry.SEEDS_HEADING)
    if section is None:
        return []
    seeds: list[SeedItem] = []
    for sub in section.children:                       # each `### <seed-id>`
        sid = sub.title.strip()
        if not sid:
            continue
        meta = _meta_from_bullets(sub)
        summary = _first_paragraph(sub)
        status = _meta_scalar(meta, "status") or registry.DEFAULT_SEED_STATUS
        raw = {"id": sid, "status": status, "summary": summary, **meta}
        seeds.append(SeedItem(
            id=sid, status=status, summary=summary, raw=raw,
            layers=_meta_tags(meta, "layers"), services=_meta_tags(meta, "services"),
            design=_meta_scalar(meta, "design").lower(),
        ))
    return seeds


def _parse_stories(doc: markdown.MarkdownDoc, epic_name: str, root: Path,
                   epic_dir: Path) -> list[Story]:
    section = doc.find_section(registry.STORIES_HEADING)
    if section is None:
        return []
    stories: list[Story] = []
    for sub in section.children:                       # each `### <slug>`
        slug = sub.title.strip()
        if not slug:
            continue
        meta = _meta_from_bullets(sub)
        seed_items = _split_list(_meta_scalar(meta, registry.STORY_COVERS_KEY))
        rel = (epic_dir / "stories" / slug / "story.md").relative_to(root).as_posix()
        # `dependencies` is deliberately absent here: the epic states which seeds a story covers,
        # the story states what blocks it. `_attach_story_md` fills it in from the story.md.
        raw = {"slug": slug, "seedItems": seed_items, **meta}
        stories.append(Story(
            slug=slug,
            title=_meta_scalar(meta, "title"),
            path=rel,
            eid=_meta_scalar(meta, "id"),
            seed_items=seed_items,
            dependencies=[],
            raw=raw,
        ))
    return stories


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def find_root(start: Path) -> Path:
    """Walk up from *start* to the nearest dir that looks like a repo root; else *start*."""
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / ".git").exists() or (d / "docs").is_dir() \
                or (d / "ostler.yml").exists() or (d / "agents.yml").exists():
            return d
    return start


def _load_config(root: Path) -> dict:
    for name in ("ostler.yml", "ostler.yaml", "agents.yml", ".agents.yml"):
        p = root / name
        if not p.exists():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and isinstance(data.get("organization"), dict):
            return data["organization"]
    return {}


def _read_frontmatter(path: Path) -> markdown.MarkdownDoc:
    return markdown.split(path.read_text(encoding="utf-8"))


# Every location the graph knows, and its default. A key here is a `docRoots:` key, so a repo
# that files its planning documents somewhere other than `docs/` says so once and every reader
# follows — which is the whole reason no caller is allowed to spell a doc path itself.
#
# `backlog` and `roadmaps` are the two the graph used to not know about, and they arrived by
# different failures. The backlog was hardcoded here on the argument that an intake list is
# "unfiled by definition"; what that actually bought was a workflow parameter naming a second
# backlog, which the run wrote and `ostler backlog` could not see. `roadmaps` was simply never
# asked about, so the same parameter grew for it. Both are now the same kind of fact as the
# epics root.
#
# `backlog` names a *file* rather than a directory — the one entry that does, because there is
# one backlog rather than a tree of them. Callers reach it through `path.backlog_path*`, which
# is where that asymmetry is stated for readers who don't come through here.
BUILTIN_DOC_ROOTS: dict[str, str] = {
    "features": "docs/features",
    "epics": "docs/epics",
    "milestones": "docs/milestones",
    "specs": "docs/specs",
    "roadmaps": "docs/roadmaps",
    "backlog": "docs/backlog.md",
}


def doc_roots(root: Path, kinds: Sequence[dynamic_registry.TemplateKind] | None = None,
              config: dict | None = None) -> dict[str, Path]:
    """Where each kind of document lives under *root*, honouring `docRoots:` config.

    The mapping :class:`Graph` carries, derived without loading the graph — a caller that
    holds only a repo root (a workflow deriving an artifact path, say) gets the *same*
    answer as one holding a graph, including a repo that moved its epics out of `docs/`.
    Loading the graph reads every markdown file under these roots; deriving a path should
    not cost that, and a second, subtly different derivation is what this avoids.

    `kinds` and `config` are the caller's already-loaded copies, so :func:`load` does not
    read either twice.
    """
    cfg = (config if config is not None else _load_config(root)).get("docRoots") or {}
    roots = {key: root / cfg.get(key, default) for key, default in BUILTIN_DOC_ROOTS.items()}
    for kind in (dynamic_registry.load_kinds(root) if kinds is None else kinds):
        roots.setdefault(kind.doc_root, root / cfg.get(kind.doc_root, kind.default_path))
    return roots


def load(
    cwd: Path | None = None,
    *,
    root_overrides: Mapping[str, str | Path] | None = None,
) -> Graph:
    root = find_root(cwd or Path.cwd())
    config = _load_config(root)

    template_kinds = dynamic_registry.load_kinds(root)
    roots = doc_roots(root, template_kinds, config)
    for kind, configured in (root_overrides or {}).items():
        configured_path = Path(configured)
        roots[kind] = configured_path if configured_path.is_absolute() else root / configured_path

    org_name = config.get("name") or root.name
    if config.get("profile") in ("full", "exploration"):
        profile = config["profile"]
    else:
        profile = (
            "full"
            if roots["epics"].is_dir() or roots["milestones"].is_dir()
            else "exploration"
        )

    graph = Graph(root=root, org_name=org_name, profile=profile, doc_roots=roots,
                  template_kinds=template_kinds)

    _load_features(graph)
    _load_ui_nodes(graph)
    if profile == "full":
        _load_milestones(graph)
        _load_epics(graph)
        _load_ids(graph)
    return graph


def _load_ids(graph: Graph) -> None:
    p = graph.root / ".agents" / "ids.json"
    if p.exists():
        try:
            graph.ids = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            graph.ids = None


#: The read-only document memo: one parsed :class:`markdown.MarkdownDoc` per path, with the
#: content digest it was parsed from and the store it has been written to. Process-lifetime,
#: in front of the persistent index — a run reads the same file from four places and must not
#: pay four lookups for it.
#:
#: The store is part of the memo's identity: an entry only answers the store it was computed
#: under, exactly as `inventory._SYMBOL_MEMO` does. One process can open more than one —
#: ``--verify-index`` opens two, and a long-lived :class:`ostler.Ostler` opens one per book.
#:
#: Serving a document across stores looks safe, on the argument that these products are a pure
#: function of the bytes and so no store can disagree about them. That argument is the one
#: ``--verify-index`` exists to *test*, and assuming it is what made the mode inert: the mode
#: runs the indexed and the uncached path in one process and diffs the reports, so a memo
#: spanning both let the uncached half read the products the indexed half had already parsed.
#: A store that round-trips a document wrongly was therefore never read on the half that was
#: supposed to catch it, and the gate passed on a corrupted entry. The document is the largest
#: product the index holds, which made it the largest hole in the gate.
@dataclass
class _Cached:
    """One path's read-only products, held for the life of the process."""

    digest: str
    doc: markdown.MarkdownDoc
    store: index.IndexStore | None       # the store this content was computed under, if any
    ui_nodes: list[UINode] | None        # stored form, straight off the entry; see `_DocProducts`


_DOC_CACHE: dict[Path, _Cached] = {}

@dataclass(frozen=True)
class _DocProducts:
    """An index entry's payload: everything a reader wants off a document that costs a parse.

    The frontmatter, the byte-exact halves the sections index into, and the section tree itself
    (which carries the bullets, the tables and the links). A class rather than a dict so the
    shape check on the way back in is one ``isinstance`` — a payload from an older build names
    a class this one no longer has, and unpickling it raises, which the store already reads as
    the miss it is.
    """

    frontmatter: dict | None
    raw_frontmatter: str
    body: str
    sections: list[markdown.Section]
    #: The file's UI nodes, in *stored* form — every ``UINode.path`` blanked, because it is the
    #: one part of a node that is not a function of the file's bytes and its repo-relative path,
    #: and an entry is shared between every checkout of the repo. Re-bound on the way out.
    #:
    #: ``None`` when nothing has derived them yet: the accessor is reached for stories, epics and
    #: link targets too, and only :func:`_feature_doc` has the repo root a node's id is minted
    #: against. Such an entry is completed in place the first time a run does want them.
    ui_nodes: list[UINode] | None = None


def read_doc(path: Path) -> markdown.MarkdownDoc:
    """The parsed document at *path* — **shared, and for read-only callers only**.

    One `doctor` run reads the same feature document four times over: the graph load wants its
    frontmatter, the UI-node load wants its sections, the per-file UI check re-splits it,
    conformance re-splits it again, and the link resolver splits every file a link points into
    so it can list that file's anchors. Each is the same parse of the same bytes, and on a real
    book that splitting is most of the wall clock. This is the one place those readers go.

    Two caches sit behind it, both keyed on the file's **content digest** rather than its mtime.
    A load is not the only thing that touches these files — the writer phases of a workflow edit
    them between loads, and a same-size rewrite inside one filesystem timestamp tick is exactly
    the case a stat-keyed cache serves stale. Reading the bytes is required to hash them, and
    reading the whole book costs 0.03s against the tens of seconds it saves. In front is
    :data:`_DOC_CACHE`, for the life of the process; behind it is :mod:`ostler.index`, for the
    life of the machine, since every ``ostler`` invocation is a fresh process.

    **A writer must not come through here.** ``MarkdownDoc.replace_body`` mutates in place and
    drops the document's parsed sections, so a writer served this instance would leave every
    later reader in the run holding a document that no longer matches the file. The mutating
    call sites keep calling ``markdown.split`` for themselves, which is what makes serving a
    shared instance safe at all.

    Raises ``OSError`` when the file cannot be read, as ``read_text`` did at each of the call
    sites this replaced — absence is the caller's finding to report, not this function's.
    """
    target = Path(path)
    data = target.read_bytes()
    digest = index.content_sha(data)
    store = index.active()
    cached = _DOC_CACHE.get(target)
    if cached is not None and cached.digest == digest and cached.store is store:
        return cached.doc
    cached = _read_products(target, data, digest, store)
    _DOC_CACHE[target] = cached
    return cached.doc


def _read_products(path: Path, data: bytes, digest: str,
                   store: index.IndexStore | None) -> _Cached:
    """*path*'s products, from the index when it has them and from the parser when it does not.

    Outside a session *store* is ``None`` and this is the cold path — which is the right reading,
    because a command that opened no index has no index, and that must never be an error.
    """
    payload = _products_of(store.get(path, sha=digest)) if store is not None else None
    if payload is not None:
        return _Cached(digest, _doc_from_products(payload), store, payload.ui_nodes)
    doc = markdown.split(data.decode("utf-8"))
    # Force the lazy section parse now. The sections — and the bullets, tables and links hanging
    # off them — are the expensive half, and an entry carrying only the frontmatter would make
    # every warm reader re-parse the body the entry was supposed to save it from.
    _ = doc.sections
    cached = _Cached(digest, doc, store, None)
    if store is not None:
        _persist(store, path, cached)
    return cached


def _persist(store: index.IndexStore, path: Path, cached: _Cached) -> None:
    """Write *cached*'s products to *store*, and record that this content is now in it."""
    store.put(path, _DocProducts(
        frontmatter=cached.doc.frontmatter, raw_frontmatter=cached.doc.raw_frontmatter,
        body=cached.doc.body, sections=cached.doc.sections, ui_nodes=cached.ui_nodes,
    ), sha=cached.digest)
    cached.store = store


def _products_of(payload: object) -> _DocProducts | None:
    """*payload* as this build's entry shape, or ``None`` when it is not one.

    Shape-checked rather than trusted: the store guarantees the payload is something *this*
    build wrote, not that it is this particular product, and a malformed entry has to read as a
    miss like every other kind of damage.
    """
    return payload if isinstance(payload, _DocProducts) else None


def _doc_from_products(payload: _DocProducts) -> markdown.MarkdownDoc:
    return markdown.MarkdownDoc(
        frontmatter=payload.frontmatter, raw_frontmatter=payload.raw_frontmatter,
        body=payload.body, _sections=payload.sections)


#: Per-path UI nodes, held against the *identity* of the document they were parsed from.
#: :func:`read_doc` hands back the same instance while the file's content has not moved, so
#: identity is the freshness test — and re-deriving the nodes is the only thing left to skip.
_FEATURE_DOC_CACHE: dict[Path, tuple[markdown.MarkdownDoc, dict, list[UINode]]] = {}


def _feature_doc(path: Path, root: Path) -> tuple[dict, list[UINode]]:
    """The two products the feature book is read for — frontmatter and UI nodes — parsed once.

    Two things were paying full markdown parses of the same files. :func:`_load_features` wanted
    only the frontmatter, but ``markdown.split`` locates the fence with the parser rather than by
    scanning for ``---`` (deliberately — a line scan lost CRLF files and trailing-space fences
    entirely), so "just the frontmatter" costs a parse too; :func:`_load_ui_nodes` then read and
    parsed every file a second time for its sections. Measured on a real book: 5.7s and 18.7s of
    a 25s load. One pass produces both.

    The parse itself now comes from :func:`read_doc`, so the same pass also serves the per-file
    UI check, conformance and the link resolver — and the nodes derived here go back into the
    same entry, because deriving them is a second markdown pass per node (``extract_refs`` on
    each node's region) and was 15s of a warm 20s load on a real book.

    The one part of a node that is *not* a function of the file's bytes is ``UINode.path``, an
    absolute path into this checkout; it is blanked on the way in and re-bound on the way out, so
    two worktrees of the same repo share the entry rather than fighting over it. The node's *id*
    is repo-relative already, and the entry's key carries that same repo-relative path.

    What is cached is shared across every graph loaded in this process, so callers read these
    products and do not mutate them — as every consumer of ``graph.ui_nodes`` and
    ``FeatureRecord.data`` does today. The frontmatter is copied out because a ``FeatureRecord``
    hands it to callers directly; the nodes are not, because copying them is the cost this is
    avoiding.
    """
    doc = read_doc(path)
    hit = _FEATURE_DOC_CACHE.get(path)
    if hit is not None and hit[0] is doc:
        return dict(hit[1]), hit[2]
    frontmatter = doc.frontmatter or {}
    nodes = _ui_nodes(doc, path, root)
    _FEATURE_DOC_CACHE[path] = (doc, frontmatter, nodes)
    return dict(frontmatter), nodes


def _ui_nodes(doc: markdown.MarkdownDoc, path: Path, root: Path) -> list[UINode]:
    """*path*'s UI nodes: off the index entry when it carries them, derived and stored when not.

    The entry the accessor already read is completed in place, rather than given a key of its
    own: a document and its nodes go stale together — they are the same bytes — and one entry
    per file is one write and one read instead of two.
    """
    cached = _DOC_CACHE.get(path)
    if cached is not None and cached.ui_nodes is not None:
        # Copied out rather than re-bound in place: the stored form stays stored, so a store this
        # process has not written to yet still gets the nodes and not just the document.
        return [replace(node, path=path) for node in cached.ui_nodes]
    nodes = _parse_ui_nodes(doc, path, root)
    if cached is not None and cached.doc is doc:
        cached.ui_nodes = [replace(node, path=Path()) for node in nodes]
        store = index.active()
        if store is not None:
            _persist(store, path, cached)
    return nodes


def _feature_paths(graph: Graph) -> list[Path]:
    froot = graph.doc_roots["features"]
    if not froot.is_dir():
        return []
    return [p for p in sorted(froot.rglob("*.md"))
            if p.is_file() and p.name not in registry.RESERVED_FILES]


def _load_features(graph: Graph) -> None:
    froot = graph.doc_roots["features"]
    for path in _feature_paths(graph):
        try:
            data, _ = _feature_doc(path, graph.root)
        except OSError:
            continue
        rel = path.relative_to(froot).with_suffix("")
        slug = str(data.get("slug") or rel.name)
        area = str(data.get("area") or (rel.parent.as_posix() if rel.parent.as_posix() != "." else ""))
        title = str(data.get("title") or slug)
        graph.features.append(FeatureRecord(slug=slug, area=area, title=title, path=path, data=data))


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if _is_list_value(str(v).strip())]
    return [p.strip() for p in str(value).split(",") if _is_list_value(p.strip())]


def _is_list_value(value: str) -> bool:
    return bool(value) and value.lower() not in {"none", "(none)", "[]"}


def _load_milestones(graph: Graph) -> None:
    mroot = graph.doc_roots["milestones"]
    if not mroot.is_dir():
        return
    for path in sorted(mroot.glob("*.md")):
        if not path.is_file() or path.name in registry.RESERVED_FILES:
            continue
        try:
            doc = _read_frontmatter(path)
        except OSError:
            continue
        fm = doc.frontmatter or {}
        if registry.base_type(registry.type_of(fm)) != "milestone":
            continue
        graph.milestones.append(Milestone(
            name=path.stem,
            path=path,
            title=str(fm.get("title") or path.stem),
            status=str(fm.get("status") or ""),
            eid=str(fm.get("id") or path.stem),
            depends_on=_as_list(fm.get("dependsOn") or fm.get("depends_on")),
            source_items=_as_list(fm.get("sourceItems") or fm.get("source_items")),
            epics=_as_list(fm.get("epics")),
        ))


_ANCHOR_STRIP_RE = re.compile(r"[^\w\s-]")
_ANCHOR_SPACE_RE = re.compile(r"\s+")


def anchor_of(title: str) -> str:
    """GitHub-style heading anchor: lowercase, spaces→hyphens, punctuation dropped."""
    s = _ANCHOR_STRIP_RE.sub("", title.strip().lower())
    return _ANCHOR_SPACE_RE.sub("-", s).strip("-")


def _file_main_section(doc: markdown.MarkdownDoc) -> markdown.Section | None:
    """The node's own region: its H1 (whose bullets are the file node's metadata), else preamble."""
    for s in doc.sections:
        if s.level == 1:
            return s
    return doc.sections[0] if doc.sections else None


def _inline_type(title: str) -> tuple[str | None, str]:
    """``field: timeout`` **or** the colon-less ``field timeout`` → (type, description) when the
    first token is a **known** UI type; otherwise ``(None, title)``. A first word that isn't a real
    type (``Contract``, ``The ladder``) is left for the caller to promote as ``untyped``.
    Inline-typed headings are always *section* nodes, whatever the type's usual file/section kind."""
    prefix, sep, rest = title.partition(":")
    if sep and registry.UI_TYPES_BY_NAME.get(prefix.strip().lower()) is not None:
        return registry.UI_TYPES_BY_NAME[prefix.strip().lower()].name, rest.strip()
    first, _, rest2 = title.partition(" ")
    t = registry.UI_TYPES_BY_NAME.get(first.strip().lower())
    if t is not None and rest2.strip():
        return t.name, rest2.strip()
    return None, title


def _promote_section(section: markdown.Section, rel: str, path: Path, offset: int,
                     parent_id: str, container_type: str | None, nodes: list[UINode]) -> None:
    """Promote **every** heading to a section node so its links are captured and it nests. Its type
    comes from an inline ``type:`` prefix / first-word (`### field: timeout`, `## field timeout`) or
    its enclosing container (`## Methods` → its children are ``method``s); a heading that names no
    real type is promoted as **``untyped``** (caught by ``--title``, not a garbage type). Nesting
    composes at any depth: each node is the ``parent`` of its descendants."""
    title = section.title.strip()
    if not title:
        return
    # A registered container heading (`## Components`/`## Methods`/…) isn't itself a node; it
    # types its *direct* children. Containers work at any depth, so nesting composes.
    child_container = registry.UI_HEADING_TO_TYPE.get(title)
    if child_container is not None:
        for sub in section.children:
            _promote_section(sub, rel, path, offset, parent_id, child_container, nodes)
        return
    ntype, ntitle = _inline_type(title)                # inline type: / first word wins…
    ntype = ntype or container_type or "untyped"       # …else container's type, else untyped
    anchor = anchor_of(title)                          # the rendered heading anchor
    node_id = f"{rel}#{anchor}"
    nodes.append(UINode(
        type=ntype, kind="section", id=node_id, path=path, anchor=anchor,
        title=ntitle, level=section.level, parent=parent_id,
        line=offset + section.line_start + 1,
        meta=_meta_from_bullets(section), bullet_order=_bullet_pairs(section),
        links=section.refs.links,
    ))
    # container_type applies only to a container's direct children, so it resets on descent.
    for sub in section.children:
        _promote_section(sub, rel, path, offset, node_id, None, nodes)


def _parse_ui_nodes(doc: markdown.MarkdownDoc, path: Path, root: Path) -> list[UINode]:
    """File-level node (if the frontmatter `type:` is a UI file-type) + every typed section node,
    nested. A section is typed by its enclosing container heading or an inline `type:` prefix; see
    `_promote_section`."""
    rel = path.relative_to(root).as_posix()
    offset = doc.body_offset
    nodes: list[UINode] = []

    fm = doc.frontmatter or {}
    ftype = registry.ui_type(registry.type_of(fm))
    main = _file_main_section(doc)
    file_id = ""
    if ftype is not None and ftype.kind == "file":
        meta = _meta_from_bullets(main) if main else {}
        order = _bullet_pairs(main) if main else []
        # The file node's own region = its H1 content up to the first `## Heading` child, so its
        # links don't overlap the section nodes' links (keeps the linter from double-reporting).
        if main is not None:
            own_end = min((c.line_start for c in main.children), default=main.line_end)
            text = "\n".join(main.body_lines[main.line_start:own_end])
            line = offset + main.line_start + 1
        else:
            text, line = doc.body, offset + 1
        file_id = rel
        nodes.append(UINode(
            type=ftype.name, kind="file", id=rel, path=path, level=1, parent="",
            title=str(fm.get("title") or (main.title if main else rel)),
            line=line, meta=meta, bullet_order=order,
            links=markdown.extract_refs(text).links, data=fm,
        ))

    # Recurse the heading tree: the H1's children (or the doc's root sections) hang off the file node.
    top = main.children if (main is not None and main.level == 1) else doc.sections
    for sec in top:
        _promote_section(sec, rel, path, offset, file_id, None, nodes)
    return nodes


def _load_ui_nodes(graph: Graph) -> None:
    for path in _feature_paths(graph):
        try:
            _, nodes = _feature_doc(path, graph.root)
        except OSError:
            continue
        graph.ui_nodes.extend(nodes)


def _load_epics(graph: Graph) -> None:
    eroot = graph.doc_roots["epics"]
    if not eroot.is_dir():
        return
    for d in sorted(eroot.iterdir()):
        if not d.is_dir():
            continue
        epic_md = d / "epic.md"
        if not epic_md.exists():
            continue

        doc = _read_frontmatter(epic_md)
        fm = doc.frontmatter or {}
        epic = Epic(
            name=d.name,
            directory=d,
            title=str(fm.get("title") or ""),
            status=str(fm.get("status") or ""),
            eid=str(fm.get("id") or ""),
            epic_md=epic_md,
        )
        epic.seeds = _parse_seeds(doc)
        for story in _parse_stories(doc, epic.name, graph.root, d):
            _attach_story_md(graph, epic, story)
            epic.stories.append(story)
        graph.epics.append(epic)


def _attach_story_md(graph: Graph, epic: Epic, story: Story) -> None:
    candidates = []
    if story.path:
        candidates.append(graph.root / story.path)
    candidates.append(epic.directory / "stories" / story.slug / "story.md")
    for c in candidates:
        if c.exists() and c.is_file():
            story.story_md = c
            doc = markdown.split(c.read_text(encoding="utf-8"))
            if doc.frontmatter:
                story.file_eid = str(doc.frontmatter.get("id") or "")
                story.external_key = str(doc.frontmatter.get("externalKey") or "")
                story.raw["externalKey"] = story.external_key
            if not story.eid and story.file_eid:
                # crud writes the minted id in both places; a story whose epic block
                # predates that still carries it in its own frontmatter.
                story.eid = story.file_eid
            refs = doc.refs
            story.doc_refs = refs.doc_hrefs
            story.status = story_status(doc)
            story.body_status = story_body_status(doc)
            story.dependencies = story_dependencies(doc)
            story.raw["dependencies"] = story.dependencies
            story.dependency_strays = story_dependency_strays(doc)
            story.fixtures = story_fixtures(doc)
            story.fixture_strays = story_fixture_strays(doc)
            problems = required_section_problems(doc, registry.STORY_SECTIONS)
            story.unwritten_sections = [s.heading for s, _ in problems]
            story.unwritten_detail = [f"{s.heading} ({why})" for s, why in problems]
            story.misordered_sections = section_order_problems(doc, registry.STORY_SECTIONS)
            return
