"""The unified organization model: load the typed knowledge graph from markdown Concepts.

Every entity is an OKF Concept (markdown + frontmatter); see ``SPEC.md`` and ``registry.py``. An
epic's seeds and story dependency-DAG are folded into its ``epic.md`` body (``## Seeds`` /
``## Stories``) and read back with the hierarchical markdown parser — there are no ``seed.json`` /
``dependencies.json`` files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import dynamic_registry, markdown, registry

# Seed statuses that no longer require story coverage.
INACTIVE_SEED_STATUS = registry.INACTIVE_SEED_STATUS


@dataclass
class SeedItem:
    id: str
    status: str
    summary: str = ""
    raw: dict = field(default_factory=dict)

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
    raw: dict = field(default_factory=dict)
    story_md: Path | None = None
    status: str = ""
    knowledge_refs: list[str] = field(default_factory=list)


@dataclass
class Epic:
    name: str
    directory: Path
    title: str = ""
    status: str = ""
    eid: str = ""                       # allocated id from frontmatter (e.g. "pred-15")
    epic_md: Path | None = None
    seeds: list[SeedItem] = field(default_factory=list)
    stories: list[Story] = field(default_factory=list)

    @property
    def seed_ids(self) -> set[str]:
        return {s.id for s in self.seeds}


@dataclass
class KnowledgeRecord:
    surface: str
    path: Path
    fmt: str  # always "md" in this format; retained for callers
    data: dict


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
    knowledge: list[KnowledgeRecord] = field(default_factory=list)
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

    def find_story(self, slug: str) -> tuple[Epic, Story] | None:
        for e in self.epics:
            for s in e.stories:
                if s.slug == slug:
                    return e, s
        return None


# ---------------------------------------------------------------------------
# epic.md body parsing  (## Seeds / ## Stories → SeedItem / Story)
# ---------------------------------------------------------------------------
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
        previous = meta.get(key)
        if previous is None:
            meta[key] = value
        elif isinstance(previous, list):
            previous.append(value)
        else:
            meta[key] = [previous, value]
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
        seeds.append(SeedItem(id=sid, status=status, summary=summary, raw=raw))
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


def load(cwd: Path | None = None) -> Graph:
    root = find_root(cwd or Path.cwd())
    config = _load_config(root)

    doc_root_cfg = config.get("docRoots") or {}
    doc_roots = {
        key: root / doc_root_cfg.get(key, f"docs/{key}")
        for key in ("features", "epics", "knowledge", "specs")
    }

    template_kinds = dynamic_registry.load_kinds(root)
    for kind in template_kinds:
        doc_roots.setdefault(kind.doc_root, root / doc_root_cfg.get(kind.doc_root, kind.default_path))

    org_name = config.get("name") or root.name
    if config.get("profile") in ("full", "exploration"):
        profile = config["profile"]
    else:
        profile = "full" if doc_roots["epics"].is_dir() else "exploration"

    graph = Graph(root=root, org_name=org_name, profile=profile, doc_roots=doc_roots,
                  template_kinds=template_kinds)

    _load_knowledge(graph)
    _load_features(graph)
    _load_ui_nodes(graph)
    if profile == "full":
        _load_epics(graph)
        _load_ids(graph)
    return graph


def _load_ids(graph: Graph) -> None:
    import json
    p = graph.root / ".agents" / "ids.json"
    if p.exists():
        try:
            graph.ids = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            graph.ids = None


def _load_knowledge(graph: Graph) -> None:
    kroot = graph.doc_roots["knowledge"]
    if not kroot.is_dir():
        return
    for path in sorted(kroot.rglob("*.md")):
        if not path.is_file() or path.name in registry.RESERVED_FILES:
            continue
        try:
            doc = _read_frontmatter(path)
        except OSError:
            continue
        data = doc.frontmatter or {}
        surface = str(data.get("surface") or path.relative_to(kroot).with_suffix("").as_posix())
        graph.knowledge.append(KnowledgeRecord(surface=surface, path=path, fmt="md",
                                               data=data))


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
            story.knowledge_refs = refs.knowledge_paths
            fm = doc.frontmatter or {}
            status = fm.get("status")
            if not status:
                sec = doc.find_section("Implementation Status")
                m = re.search(r"\*\*Status\*\*:\s*(.+)", sec.text if sec else doc.body)
                if m:
                    status = m.group(1).strip()
            story.status = str(status or "")
            return
