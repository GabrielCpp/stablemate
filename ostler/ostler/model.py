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
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ostler import dynamic_registry, markdown, registry

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

    @property
    def active(self) -> bool:
        return self.status not in INACTIVE_SEED_STATUS


@dataclass
class Story:
    slug: str
    title: str
    path: str
    seed_items: list[str]
    dependencies: list[str]
    # Allocated id, repo-prefixed (e.g. "TODO-15"). Minted by ostler when the story is
    # created, recorded both in the epic's `## Stories` block and in the story's own
    # frontmatter — mirroring Epic.eid so a story is addressable by id, not only by slug.
    eid: str = ""
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

    @property
    def authored(self) -> bool:
        """Whether the story says anything: it has a story.md and honors the body contract.

        Orthogonal to :attr:`status` — that tracks *build* progress (Not started → QA passed),
        this tracks whether there is a spec to build from at all.
        """
        return self.story_md is not None and not self.unwritten_sections


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

    def find_story(self, slug: str) -> tuple[Epic, Story] | None:
        for e in self.epics:
            for s in e.stories:
                if s.slug == slug:
                    return e, s
        return None


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


def _meta_from_bullets(section: markdown.Section) -> dict[str, str | list[str]]:
    """Parse the leading `- key: value` metadata bullets of a section into an ordered dict.

    Keys are lowercased; the first ``:`` separates key and value (so ``depends on: a, b`` keeps the
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
    """Parse a `covers:`/`depends on:` value into a list, honoring the empty tokens."""
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
        dependencies = _split_list(_meta_scalar(meta, registry.STORY_DEPENDS_KEY))
        rel = (epic_dir / "stories" / slug / "story.md").relative_to(root).as_posix()
        raw = {"slug": slug, "seedItems": seed_items, "dependencies": dependencies, **meta}
        stories.append(Story(
            slug=slug,
            title=_meta_scalar(meta, "title"),
            path=rel,
            eid=_meta_scalar(meta, "id"),
            seed_items=seed_items,
            dependencies=dependencies,
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
    roots = {key: root / cfg.get(key, f"docs/{key}")
             for key in ("features", "epics", "milestones", "specs")}
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


def _load_features(graph: Graph) -> None:
    froot = graph.doc_roots["features"]
    if not froot.is_dir():
        return
    for path in sorted(froot.rglob("*.md")):
        if not path.is_file() or path.name in registry.RESERVED_FILES:
            continue
        try:
            doc = _read_frontmatter(path)
        except OSError:
            continue
        data = doc.frontmatter or {}
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
        meta=_meta_from_bullets(section), links=section.refs.links,
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
            line=line, meta=meta, links=markdown.extract_refs(text).links, data=fm,
        ))

    # Recurse the heading tree: the H1's children (or the doc's root sections) hang off the file node.
    top = main.children if (main is not None and main.level == 1) else doc.sections
    for sec in top:
        _promote_section(sec, rel, path, offset, file_id, None, nodes)
    return nodes


def _load_ui_nodes(graph: Graph) -> None:
    froot = graph.doc_roots["features"]
    if not froot.is_dir():
        return
    for path in sorted(froot.rglob("*.md")):
        if not path.is_file() or path.name in registry.RESERVED_FILES:
            continue
        try:
            doc = markdown.split(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        graph.ui_nodes.extend(_parse_ui_nodes(doc, path, graph.root))


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
            refs = doc.refs
            story.doc_refs = refs.doc_hrefs
            story.status = story_status(doc)
            story.body_status = story_body_status(doc)
            story.unwritten_sections = [
                s.heading for s, _ in required_section_problems(doc, registry.STORY_SECTIONS)
            ]
            return
