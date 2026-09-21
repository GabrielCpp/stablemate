"""The unified organization model: load the typed knowledge graph from markdown Concepts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from ostler import dynamic_registry, index, markdown, registry

INACTIVE_SEED_STATUS = registry.INACTIVE_SEED_STATUS


@dataclass
class SeedItem:
    id: str
    status: str
    summary: str = ""
    raw: dict = field(default_factory=dict)
    layers: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    design: str = ""

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
    eid: str = ""
    external_key: str = ""
    file_eid: str = ""
    raw: dict = field(default_factory=dict)
    story_md: Path | None = None
    status: str = ""
    body_status: str = ""
    conflict: str = ""
    doc_refs: list[str] = field(default_factory=list)
    unwritten_sections: list[str] = field(default_factory=list)
    unwritten_detail: list[str] = field(default_factory=list)
    dependency_strays: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    fixture_strays: list[str] = field(default_factory=list)
    misordered_sections: list[str] = field(default_factory=list)

    @property
    def authored(self) -> bool:
        """Whether the story says anything: it has a story.md and honors the body contract."""
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
    eid: str = ""
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
    """A node of the OKF UI profile (docs/okf-ui-profile.md)."""
    type: str
    kind: str
    id: str
    path: Path
    anchor: str = ""
    title: str = ""
    line: int = 0
    level: int = 0
    parent: str = ""
    meta: dict = field(default_factory=dict)
    bullet_order: list[tuple[str, str, int]] = field(default_factory=list)
    bullet_lines: dict[int, int] = field(default_factory=dict)
    combiners: dict[int, str] = field(default_factory=dict)
    entries: dict[str, list[Entry]] = field(default_factory=dict)
    records: dict[str, dict[str, str | list[str]]] = field(default_factory=dict)
    links: list[tuple[str, str, int]] = field(default_factory=list)
    data: dict = field(default_factory=dict)


@dataclass
class Graph:
    root: Path
    org_name: str
    profile: str
    doc_roots: dict[str, Path]
    epics: list[Epic] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    features: list[FeatureRecord] = field(default_factory=list)
    ui_nodes: list[UINode] = field(default_factory=list)
    surfaces: dict[str, dict] = field(default_factory=dict)
    ids: dict | None = None
    template_kinds: tuple = ()

    def ui_nodes_of_type(self, type_name: str) -> list[UINode]:
        return [n for n in self.ui_nodes if n.type == type_name]

    def find_ui_node(self, ident: str) -> UINode | None:
        """Look up a UI node by its identity (repo-relative path, or ``path#anchor``)."""
        for n in self.ui_nodes:
            if n.id == ident:
                return n
        return None

    def resolve_doc_ref(self, href: str, *, origin: Path | None = None) -> str:
        """Normalize a document link into a node identity (``<repo-rel-path>[#anchor]``)."""
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
            except ValueError:
                pass
        candidates.append(path_part.lstrip("/"))

        rel = next((c for c in candidates if (self.root / c).is_file()), candidates[0])
        return f"{rel}#{anchor}" if anchor else rel

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
        """The story named by an id, external key, or slug."""
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


def required_section_problems(
    doc: markdown.MarkdownDoc,
    specs: tuple[registry.SectionSpec, ...],
) -> list[tuple[registry.SectionSpec, str]]:
    """``(spec, "missing"|"empty")`` for every required section the body does not honor."""
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
    """The required headings this body places out of the contract's order, as messages."""
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
    """The ``- **Status**:`` field of a parsed story doc, or ``None``."""
    section = doc.find_section(registry.STORY_STATUS_HEADING)
    if section is not None:
        return section.labelled(registry.STORY_STATUS_LABEL)
    return doc.find_bullet(registry.STORY_STATUS_LABEL)


def story_status(doc: markdown.MarkdownDoc) -> str:
    """A story's status: frontmatter ``status:`` first, else the parsed bullet (``""`` if neither)."""
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
    """The values of every ``- <label>: <value>`` bullet under ``## <heading>``, in order."""
    section = doc.find_section(heading)
    if section is None:
        return []
    want = label.strip().lower()
    values: list[str] = []
    for top in section.bullets:
        for bullet in top.walk():
            if bullet.label != want:
                continue
            values += [value for value in _split_list(bullet.value) if value not in values]
    return values


def _labelled_strays(doc: markdown.MarkdownDoc, heading: str, label: str) -> list[str]:
    """Bullets under ``## <heading>`` stating something other than ``- <label>:``."""
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
    """The sibling slugs a story's ``## Dependencies`` section says block it."""
    return _labelled_values(doc, registry.STORY_DEPS_HEADING, registry.STORY_DEPS_LABEL)


def story_fixtures(doc: markdown.MarkdownDoc) -> list[str]:
    """The declared QA fixtures a story's ``## Fixtures`` section says its plan arranges with."""
    return _labelled_values(doc, registry.STORY_FIXTURES_HEADING, registry.STORY_FIXTURES_LABEL)


def story_fixture_strays(doc: markdown.MarkdownDoc) -> list[str]:
    """Bullets under ``## Fixtures`` that state something other than ``- Fixture:``."""
    return _labelled_strays(doc, registry.STORY_FIXTURES_HEADING, registry.STORY_FIXTURES_LABEL)


def story_dependency_strays(doc: markdown.MarkdownDoc) -> list[str]:
    """Bullets under ``## Dependencies`` that state something other than ``- Blocked by:``."""
    return _labelled_strays(doc, registry.STORY_DEPS_HEADING, registry.STORY_DEPS_LABEL)


def _combiner(bullet: markdown.Bullet) -> str:
    """The claim combiner a nested bullet states in its own value, or ``""`` if it states none."""
    if not bullet.children:
        return ""
    text = bullet.text.strip()
    idx = markdown.label_colon_index(text)
    value = text[idx + 1:].strip().lower() if idx != -1 else ""
    return value if value in registry.CLAIM_COMBINERS else ""


def _bullet_combiners(section: markdown.Section) -> dict[int, str]:
    """Every stated claim combiner of a section, by the bullet ordinal `_bullet_pairs` counts in."""
    return {i: word for i, bullet in enumerate(section.bullets) if (word := _combiner(bullet))}


@dataclass(frozen=True)
class Entry:
    """One item of an ``entries=True`` key's nested list, with what it states about itself."""

    headline: str
    properties: dict[str, str | list[str]] = field(default_factory=dict)

    def property_text(self, name: str) -> str:
        """One property as the single string the book wrote, or ``""`` when it stated none."""
        value = self.properties.get(name)
        if isinstance(value, list):
            return " ".join(str(v).strip() for v in value if str(v).strip())
        return str(value).strip() if value is not None else ""


def _fold_bullets(bullets: "list[markdown.Bullet]") -> dict[str, str | list[str]]:
    """``- key: value`` children folded into a dict, deeper descendants flattened into the value."""
    folded: dict[str, str | list[str]] = {}
    for bullet in bullets:
        text = bullet.text.strip()
        idx = markdown.label_colon_index(text)
        if idx == -1:
            continue
        key, value = text[:idx], text[idx + 1:]
        key = key.strip().lower()
        nested = [item.text.strip() for child in bullet.children for item in child.walk()]
        values = [item for item in (value.strip(), *nested) if item]
        parsed: str | list[str] = "" if not values else values[0] if len(values) == 1 else values
        previous = folded.get(key)
        if previous is None:
            folded[key] = parsed
        elif isinstance(previous, list):
            previous.extend(values)
        else:
            folded[key] = [previous, *values]
    return folded


def _entries(bullet: markdown.Bullet) -> list[Entry]:
    """The entries of one ``entries=True`` bullet, in document order."""
    return [Entry(headline=text, properties=_fold_bullets(child.children))
            for child in bullet.children if (text := child.text.strip())]


def _entries_from_bullets(section: markdown.Section,
                          uitype: "registry.UINodeType | None") -> dict[str, list[Entry]]:
    """Every ``entries=True`` key of a section, with its entries — the properties `meta` drops."""
    if uitype is None:
        return {}
    found: dict[str, list[Entry]] = {}
    for bullet in section.bullets:
        text = bullet.text.strip()
        idx = markdown.label_colon_index(text)
        if idx == -1:
            continue
        key = text[:idx].strip().lower()
        spec = uitype.bullet_by_key.get(key)
        if spec is None or not spec.entries:
            continue
        found.setdefault(key, []).extend(_entries(bullet))
    return found


def _records_from_bullets(section: markdown.Section,
                          uitype: "registry.UINodeType | None"
                          ) -> dict[str, dict[str, str | list[str]]]:
    """Every ``record=True`` key of a section, with the named properties `meta` flattens away."""
    if uitype is None:
        return {}
    children: dict[str, list[markdown.Bullet]] = {}
    for bullet in section.bullets:
        text = bullet.text.strip()
        idx = markdown.label_colon_index(text)
        if idx == -1:
            continue
        key = text[:idx].strip().lower()
        spec = uitype.bullet_by_key.get(key)
        if spec is None or not spec.record:
            continue
        children.setdefault(key, []).extend(bullet.children)
    return {key: _fold_bullets(bullets) for key, bullets in children.items()}


def _nested_values(key: str, bullet: markdown.Bullet, uitype: "registry.UINodeType | None") -> list[str]:
    """A bullet's nested values, one string per value the grammar says its children hold."""
    spec = uitype.bullet_by_key.get(key) if uitype is not None else None
    if spec is not None and spec.entries:
        return [entry.headline for entry in _entries(bullet)]
    return [item.text.strip() for child in bullet.children for item in child.walk()]


def _bullet_pairs(section: markdown.Section,
                  uitype: "registry.UINodeType | None" = None) -> list[tuple[str, str, int]]:
    """Every `- key: value` of a section as ``(key, value, bullet)`` in document order."""
    pairs: list[tuple[str, str, int]] = []
    for position, bullet in enumerate(section.bullets):
        text = bullet.text.strip()
        idx = markdown.label_colon_index(text)
        if idx == -1:
            continue
        key, value = text[:idx], text[idx + 1:]
        key = key.strip().lower()
        nested = _nested_values(key, bullet, uitype)
        own = "" if _combiner(bullet) else value.strip()
        pairs.extend((key, item, position)
                     for item in (own, *nested) if item)
    return pairs


def _meta_from_bullets(section: markdown.Section,
                       uitype: "registry.UINodeType | None" = None) -> dict[str, str | list[str]]:
    """Parse the leading `- key: value` metadata bullets of a section into an ordered dict."""
    meta: dict[str, str | list[str]] = {}
    for bullet in section.bullets:
        text = bullet.text.strip()
        idx = markdown.label_colon_index(text)
        if idx == -1:
            continue
        key, value = text[:idx], text[idx + 1:]
        key = key.strip().lower()
        value = "" if _combiner(bullet) else value.strip()
        nested = _nested_values(key, bullet, uitype)
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
    """A list-valued seed meta key as normalized tags, from either spelling."""
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
    for sub in section.children:
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
    for sub in section.children:
        slug = sub.title.strip()
        if not slug:
            continue
        meta = _meta_from_bullets(sub)
        seed_items = _split_list(_meta_scalar(meta, registry.STORY_COVERS_KEY))
        rel = (epic_dir / "stories" / slug / "story.md").relative_to(root).as_posix()
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
    """Where each kind of document lives under *root*, honouring `docRoots:` config."""
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
    _load_surfaces(graph)
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


@dataclass
class _Cached:
    """One path's read-only products, held for the life of the process."""

    digest: str
    doc: markdown.MarkdownDoc
    store: index.IndexStore | None
    ui_nodes: list[UINode] | None
    links: tuple[tuple[str, str, int], ...] | None = None


_DOC_CACHE: dict[Path, _Cached] = {}

@dataclass(frozen=True)
class _DocProducts:
    """An index entry's payload: everything a reader wants off a document that costs a parse."""

    frontmatter: dict | None
    raw_frontmatter: str
    body: str
    sections: list[markdown.Section]
    ui_nodes: list[UINode] | None = None
    links: tuple[tuple[str, str, int], ...] | None = None


def read_doc(path: Path) -> markdown.MarkdownDoc:
    """The parsed document at *path* — **shared, and for read-only callers only**."""
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
    """*path*'s products, from the index when it has them and from the parser when it does not."""
    payload = _products_of(store.get(path, sha=digest)) if store is not None else None
    if payload is not None:
        return _Cached(digest, _doc_from_products(payload), store, payload.ui_nodes, payload.links)
    doc = markdown.split(data.decode("utf-8"))
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
        links=cached.links,
    ), sha=cached.digest)
    cached.store = store


def read_links(path: Path) -> tuple[tuple[str, str, int], ...]:
    """Every link in the file at *path*, outside code, as ``(text, href, line)``."""
    target = Path(path)
    doc = read_doc(target)
    cached = _DOC_CACHE[target]
    if cached.links is not None:
        return cached.links
    data = target.read_bytes()
    links = tuple(markdown.iter_links(data.decode("utf-8")))
    if cached.doc is doc and index.content_sha(data) == cached.digest:
        cached.links = links
        store = index.active()
        if store is not None:
            _persist(store, target, cached)
    return links


def _products_of(payload: object) -> _DocProducts | None:
    """*payload* as this build's entry shape, or ``None`` when it is not one."""
    return payload if isinstance(payload, _DocProducts) else None


def _doc_from_products(payload: _DocProducts) -> markdown.MarkdownDoc:
    return markdown.MarkdownDoc(
        frontmatter=payload.frontmatter, raw_frontmatter=payload.raw_frontmatter,
        body=payload.body, _sections=payload.sections)


_FEATURE_DOC_CACHE: dict[Path, tuple[markdown.MarkdownDoc, dict, list[UINode]]] = {}


def _feature_doc(path: Path, root: Path) -> tuple[dict, list[UINode]]:
    """The two products the feature book is read for — frontmatter and UI nodes — parsed once."""
    doc = read_doc(path)
    hit = _FEATURE_DOC_CACHE.get(path)
    if hit is not None and hit[0] is doc:
        return dict(hit[1]), hit[2]
    frontmatter = doc.frontmatter or {}
    nodes = _ui_nodes(doc, path, root)
    _FEATURE_DOC_CACHE[path] = (doc, frontmatter, nodes)
    return dict(frontmatter), nodes


def _ui_nodes(doc: markdown.MarkdownDoc, path: Path, root: Path) -> list[UINode]:
    """*path*'s UI nodes: off the index entry when it carries them, derived and stored when not."""
    cached = _DOC_CACHE.get(path)
    if cached is not None and cached.ui_nodes is not None:
        return [replace(node, path=path) for node in cached.ui_nodes]
    nodes = _parse_ui_nodes(doc, path, root)
    if cached is not None and cached.doc is doc:
        cached.ui_nodes = [replace(node, path=Path()) for node in nodes]
        store = index.active()
        if store is not None:
            _persist(store, path, cached)
    return nodes


def _feature_paths(graph: Graph) -> list[Path]:
    """Every book page under the features root -- a file's membership in the corpus is a claim the file makes, not a property of where it sits, so a candidate must declare a `type` to count (the same rule `doctor._check_conformance` enforces as `okf-missing-type`, and that check walks its own `etype.location` glob independently of this function, so gating here does not silence it)."""
    froot = graph.doc_roots["features"]
    if not froot.is_dir():
        return []
    paths = []
    for p in sorted(froot.rglob("*.md")):
        if not p.is_file() or p.name in registry.RESERVED_FILES:
            continue
        try:
            fm = read_doc(p).frontmatter or {}
        except OSError:
            continue
        if registry.type_of(fm):
            paths.append(p)
    return paths


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


def _load_surfaces(graph: Graph) -> None:
    froot = graph.doc_roots["features"]
    if not froot.is_dir():
        return
    for index_md in sorted(froot.glob("*/index.md")):
        try:
            doc = _read_frontmatter(index_md)
        except OSError:
            continue
        fm = doc.frontmatter
        graph.surfaces[index_md.parent.name] = dict(fm) if isinstance(fm, dict) else {}


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
    """Slug one heading title: lowercase, spaces→hyphens, punctuation dropped."""
    s = _ANCHOR_STRIP_RE.sub("", title.strip().lower())
    return _ANCHOR_SPACE_RE.sub("-", s).strip("-")


def document_anchors(doc: markdown.MarkdownDoc) -> dict[int, str]:
    """Every heading's rendered anchor in one document, keyed by its body-relative heading line."""
    issued: set[str] = set()
    repeats: dict[str, int] = {}
    anchors: dict[int, str] = {}
    for section in sorted(doc.walk_sections(), key=lambda s: s.line_start):
        title = section.title.strip()
        if not title:
            continue
        base = anchor_of(title)
        anchor = base
        while anchor in issued:
            repeats[base] = repeats.get(base, 0) + 1
            anchor = f"{base}-{repeats[base]}"
        issued.add(anchor)
        anchors[section.line_start] = anchor
    return anchors


def _file_main_section(doc: markdown.MarkdownDoc) -> markdown.Section | None:
    """The node's own region: its H1 (whose bullets are the file node's metadata), else preamble."""
    for s in doc.sections:
        if s.level == 1:
            return s
    return doc.sections[0] if doc.sections else None


def _inline_type(title: str) -> tuple[str | None, str]:
    """``field: timeout`` **or** the colon-less ``field timeout`` → (type, description) when the first token is a **known** UI type; otherwise ``(None, title)``."""
    prefix, sep, rest = title.partition(":")
    if sep and registry.UI_TYPES_BY_NAME.get(prefix.strip().lower()) is not None:
        return registry.UI_TYPES_BY_NAME[prefix.strip().lower()].name, rest.strip()
    first, _, rest2 = title.partition(" ")
    t = registry.UI_TYPES_BY_NAME.get(first.strip().lower())
    if t is not None and rest2.strip():
        return t.name, rest2.strip()
    return None, title


def _promote_section(section: markdown.Section, rel: str, path: Path, offset: int,
                     parent_id: str, container_type: str | None, nodes: list[UINode],
                     anchors: dict[int, str]) -> None:
    """Promote **every** heading to a section node so its links are captured and it nests."""
    title = section.title.strip()
    if not title:
        return
    child_container = registry.UI_HEADING_TO_TYPE.get(title)
    if child_container is not None:
        for sub in section.children:
            _promote_section(sub, rel, path, offset, parent_id, child_container, nodes, anchors)
        return
    ntype, ntitle = _inline_type(title)
    ntype = ntype or container_type or "untyped"
    anchor = anchors[section.line_start]
    node_id = f"{rel}#{anchor}"
    uitype = registry.UI_TYPES_BY_NAME.get(ntype)
    own_end = min((c.line_start for c in section.children), default=section.line_end)
    own_text = "\n".join(section.body_lines[section.line_start:own_end])
    nodes.append(UINode(
        type=ntype, kind="section", id=node_id, path=path, anchor=anchor,
        title=ntitle, level=section.level, parent=parent_id,
        line=offset + section.line_start + 1,
        meta=_meta_from_bullets(section, uitype), bullet_order=_bullet_pairs(section, uitype),
        entries=_entries_from_bullets(section, uitype), combiners=_bullet_combiners(section),
        records=_records_from_bullets(section, uitype),
        bullet_lines={i: offset + bullet.line_start + 1 for i, bullet in enumerate(section.bullets)},
        links=[(text, href, offset + section.line_start + link_line)
               for text, href, link_line in markdown.iter_links(own_text)],
    ))
    for sub in section.children:
        _promote_section(sub, rel, path, offset, node_id, None, nodes, anchors)


def _parse_ui_nodes(doc: markdown.MarkdownDoc, path: Path, root: Path) -> list[UINode]:
    """File-level node (if the frontmatter `type:` is a UI file-type) + every typed section node, nested."""
    rel = path.relative_to(root).as_posix()
    offset = doc.body_offset
    anchors = document_anchors(doc)
    nodes: list[UINode] = []

    fm = doc.frontmatter or {}
    ftype = registry.ui_type(registry.type_of(fm))
    main = _file_main_section(doc)
    file_id = ""
    if ftype is not None and ftype.kind == "file":
        meta = _meta_from_bullets(main, ftype) if main else {}
        order = _bullet_pairs(main, ftype) if main else []
        combiners = _bullet_combiners(main) if main else {}
        entries = _entries_from_bullets(main, ftype) if main else {}
        records = _records_from_bullets(main, ftype) if main else {}
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
            line=line, meta=meta, bullet_order=order, entries=entries, combiners=combiners,
            records=records,
            bullet_lines={i: offset + bullet.line_start + 1 for i, bullet in enumerate(main.bullets)} if main else {},
            links=[(t, h, line + link_line - 1) for t, h, link_line in markdown.iter_links(text)],
            data=fm,
        ))

    top = main.children if (main is not None and main.level == 1) else doc.sections
    for sec in top:
        _promote_section(sec, rel, path, offset, file_id, None, nodes, anchors)
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
                story.conflict = str(doc.frontmatter.get("conflict") or "").strip()
            if not story.eid and story.file_eid:
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
