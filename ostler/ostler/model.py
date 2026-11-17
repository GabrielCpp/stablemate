"""The planning graph: epics, stories, seeds and milestones, loaded from markdown."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ostler import dynamic_registry, index, layout, markdown, registry
from ostler._vendor.stablemate_core import config as core_config
from ostler._vendor.stablemate_core.schema import OrganizationTable
from ostler.manifest import read_manifest

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
    services: tuple[str, ...] = ()

    @property
    def authored(self) -> bool:
        """Whether the story says anything: it has a story.md and honors the body contract."""
        return self.story_md is not None and not self.unwritten_sections

    @property
    def aliases(self) -> tuple[str, ...]:
        """Every stable spelling accepted as this story, de-duplicated in precedence order."""
        return tuple(
            dict.fromkeys(
                value for value in (self.eid, self.slug) if value
            )
        )


@dataclass
class Epic:
    name: str
    directory: Path
    title: str = ""
    slug: str = ""
    status: str = ""
    eid: str = ""
    epic_md: Path | None = None
    followups: bool = False
    seeds: list[SeedItem] = field(default_factory=list)
    stories: list[Story] = field(default_factory=list)
    unwritten_detail: list[str] = field(default_factory=list)

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
    epic_refs: list[str] = field(default_factory=list)


@dataclass
class Graph:
    root: Path
    org_name: str
    profile: str
    doc_roots: dict[str, Path]
    epics: list[Epic] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    template_kinds: tuple = ()

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

    def epic_by_ref(self, ref: str) -> Epic | None:
        """The epic *ref* names: its id, its directory, or its slug, in that order; a numbered ``NNNN-slug`` from the old layout names it by its slug."""
        ref = ref.strip()
        if not ref:
            return None
        by_id = next((e for e in self.epics if e.eid and e.eid == ref), None)
        if by_id is not None:
            return by_id
        exact = next((e for e in self.epics if e.name == ref), None)
        if exact is not None:
            return exact
        slug = registry.epic_slug(ref)
        return next((e for e in self.epics if e.slug == slug), None)

    def milestone_by_name(self, name: str) -> Milestone | None:
        """The milestone *name* names: its id, its folder, or its folder's slug without the number."""
        for milestone in self.milestones:
            if name in (milestone.name, milestone.eid):
                return milestone
        if registry.epic_seq(name) is not None:
            return None
        slug = registry.epic_slug(name)
        return next((m for m in self.milestones if registry.epic_slug(m.name) == slug), None)

    def find_story(self, ref: str) -> tuple[Epic, Story] | None:
        """The story whose id is *ref*. A slug is not a story reference: see :meth:`no_story`."""
        matches = [
            (epic, story)
            for epic in self.epics
            for story in epic.stories
            if ref and ref == story.eid
        ]
        if len(matches) > 1:
            paths = ", ".join(story.path for _, story in matches)
            raise ValueError(f"story reference {ref!r} is ambiguous: {paths}")
        return matches[0] if matches else None

    def story_by_slug(self, slug: str) -> tuple[Epic, Story] | None:
        """The story filed under *slug*, for code that walks the files themselves, never a command."""
        return next(((epic, story) for epic in self.epics for story in epic.stories
                     if story.slug == slug), None)

    def no_story(self, ref: str) -> str:
        """Why *ref* names no story: the id is unknown, or *ref* is a slug and the id is spelled out."""
        found = self.story_by_slug(ref)
        if found is None:
            return f"no story with id '{ref}'"
        story = found[1]
        if story.eid:
            return (f"'{ref}' is a story slug, not a story id; ostler commands take the id: "
                    f"{story.eid}")
        return (f"'{ref}' is a story slug and the story has no id yet; give it an `id:` first "
                f"(`ostler create story` mints one)")


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


def _labelled(bullets: "Sequence[markdown.Bullet]") -> "Iterator[tuple[int, markdown.Bullet, str, str]]":
    """Each ``- key: value`` bullet as ``(position, bullet, key, raw value)``, the key lowercased."""
    for position, bullet in enumerate(bullets):
        text = bullet.text.strip()
        idx = markdown.label_colon_index(text)
        if idx == -1:
            continue
        yield position, bullet, text[:idx].strip().lower(), text[idx + 1:]


def _nested_pairs(key: str, bullet: markdown.Bullet) -> list[tuple[str, str]]:
    """A bullet's nested values as ``(key, value)``, in document order."""
    return [(key, item.text.strip()) for child in bullet.children for item in child.walk()
            if item.text.strip()]


def _meta_from_bullets(section: markdown.Section) -> dict[str, str | list[str]]:
    """Parse the leading `- key: value` metadata bullets of a section into an ordered dict."""
    meta: dict[str, str | list[str]] = {}
    for _position, bullet, key, value in _labelled(section.bullets):
        value = value.strip()
        pairs = _nested_pairs(key, bullet)
        _merge_meta(meta, key, [item for item in (value, *(v for k, v in pairs if k == key)) if item])
        for stated, item in pairs:
            if stated != key:
                _merge_meta(meta, stated, [item])
    return meta


def _merge_meta(meta: dict[str, str | list[str]], key: str, values: list[str]) -> None:
    """Add one bullet's values for `key` to `meta`: a string for one value, a list past it."""
    parsed: str | list[str] = "" if not values else values[0] if len(values) == 1 else values
    previous = meta.get(key)
    if previous is None:
        meta[key] = parsed
    elif isinstance(previous, list):
        previous.extend(values)
    else:
        meta[key] = [previous, *values]


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
        eid = _meta_scalar(meta, "id")
        story_md = epic_dir / "stories" / (eid or slug) / "story.md"
        rel = story_md.relative_to(root).as_posix() if story_md.is_relative_to(root) else story_md.as_posix()
        raw = {"slug": slug, "seedItems": seed_items, **meta}
        stories.append(Story(
            slug=slug,
            title=_meta_scalar(meta, "title"),
            path=rel,
            eid=eid,
            seed_items=seed_items,
            dependencies=[],
            raw=raw,
        ))
    return stories


def find_root(start: Path) -> Path:
    """The artifacts repo while a workspace is active; else walk up from *start* to the nearest dir that looks like a repo root, else *start*."""
    home = core_config.docs_home(start)
    if home is not None:
        return home
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / ".git").exists() or (d / "docs").is_dir() \
                or (d / "ostler.yml").exists() or (d / "agents.yml").exists():
            return d
    return start


def load_config(root: Path) -> OrganizationTable:
    manifest = read_manifest(root)
    if manifest is None or manifest.organization is None:
        return OrganizationTable()
    return manifest.organization


BUILTIN_DOC_ROOTS: dict[str, str] = {
    "milestones": "docs/milestones",
    "decisions": "docs/decisions",
    "adrs": "docs/adrs",
}


def doc_roots(root: Path, kinds: Sequence[dynamic_registry.TemplateKind] | None = None) -> dict[str, Path]:
    """Where each kind of document lives: the kept kinds under *root*'s ``docs/``, and the stand-in shelves at the top level of the artifacts dir."""
    roots = {key: root / default for key, default in BUILTIN_DOC_ROOTS.items()}
    artifacts = core_config.resolve_artifacts_dir()
    roots["epics"] = artifacts / "epics"
    roots["specs"] = artifacts / "specs"
    roots["register"] = artifacts / "backlogs"
    for kind in (dynamic_registry.load_kinds(root) if kinds is None else kinds):
        roots.setdefault(kind.doc_root, root / kind.default_path)
    return roots


def load(
    cwd: Path | None = None,
    *,
    root_overrides: Mapping[str, str | Path] | None = None,
) -> Graph:
    root = find_root(cwd or Path.cwd())
    config = load_config(root)

    layout.check(core_config.resolve_artifacts_dir(), root)
    template_kinds = dynamic_registry.load_kinds(root)
    roots = doc_roots(root, template_kinds)
    for kind, configured in (root_overrides or {}).items():
        configured_path = Path(configured)
        roots[kind] = configured_path if configured_path.is_absolute() else root / configured_path

    org_name = config.name or root.name
    if config.profile in ("full", "exploration"):
        profile = config.profile
    else:
        profile = (
            "full"
            if roots["epics"].is_dir() or roots["milestones"].is_dir()
            else "exploration"
        )

    graph = Graph(root=root, org_name=org_name, profile=profile, doc_roots=roots,
                  template_kinds=template_kinds)

    _load_milestones(graph)
    if profile == "full":
        _load_epics(graph)
        _resolve_milestone_epics(graph)
    return graph


@dataclass
class _Cached:
    """One path's read-only products, held for the life of the process."""

    digest: str
    doc: markdown.MarkdownDoc
    store: index.IndexStore | None


_DOC_CACHE: dict[Path, _Cached] = {}

@dataclass(frozen=True)
class _DocProducts:
    """An index entry's payload: everything a reader wants off a document that costs a parse."""

    frontmatter: dict | None
    raw_frontmatter: str
    body: str
    sections: list[markdown.Section]


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
        return _Cached(digest, _doc_from_products(payload), store)
    doc = markdown.split(data.decode("utf-8"))
    _ = doc.sections
    cached = _Cached(digest, doc, store)
    if store is not None:
        _persist(store, path, cached)
    return cached


def _persist(store: index.IndexStore, path: Path, cached: _Cached) -> None:
    """Write *cached*'s products to *store*, and record that this content is now in it."""
    store.put(path, _DocProducts(
        frontmatter=cached.doc.frontmatter, raw_frontmatter=cached.doc.raw_frontmatter,
        body=cached.doc.body, sections=cached.doc.sections,
    ), sha=cached.digest)
    cached.store = store


def _products_of(payload: object) -> _DocProducts | None:
    """*payload* as this build's entry shape, or ``None`` when it is not one."""
    return payload if isinstance(payload, _DocProducts) else None


def _doc_from_products(payload: _DocProducts) -> markdown.MarkdownDoc:
    return markdown.MarkdownDoc(
        frontmatter=payload.frontmatter, raw_frontmatter=payload.raw_frontmatter,
        body=payload.body, _sections=payload.sections)


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
    for path in sorted(mroot.glob(f"*/{registry.MILESTONE_FILE}")):
        if not path.is_file():
            continue
        try:
            doc = read_doc(path)
        except OSError:
            continue
        fm = doc.frontmatter or {}
        if registry.base_type(registry.type_of(fm)) != "milestone":
            continue
        name = path.parent.name
        graph.milestones.append(Milestone(
            name=name,
            path=path,
            title=str(fm.get("title") or name),
            status=str(fm.get("status") or ""),
            eid=str(fm.get("id") or name),
            depends_on=_as_list(fm.get("dependsOn") or fm.get("depends_on")),
            source_items=_as_list(fm.get("sourceItems") or fm.get("source_items")),
            epics=_as_list(fm.get("epics")),
            epic_refs=_as_list(fm.get("epics")),
        ))


def _resolve_milestone_epics(graph: Graph) -> None:
    """Point each milestone's epic refs at the epic directories they name, an unknown ref as written."""
    for milestone in graph.milestones:
        resolved = [graph.epic_by_ref(ref) for ref in milestone.epic_refs]
        milestone.epics = [
            epic.name if epic is not None else ref
            for ref, epic in zip(milestone.epic_refs, resolved, strict=True)
        ]


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

        doc = read_doc(epic_md)
        fm = doc.frontmatter or {}
        epic = Epic(
            name=d.name,
            directory=d,
            title=str(fm.get("title") or ""),
            slug=str(fm.get("slug") or "").strip() or registry.epic_slug(d.name),
            status=str(fm.get("status") or ""),
            eid=str(fm.get("id") or ""),
            epic_md=epic_md,
            followups=fm.get("followups") is True,
        )
        epic.seeds = _parse_seeds(doc)
        epic.unwritten_detail = [
            f"{spec.heading} ({why})"
            for spec, why in required_section_problems(doc, registry.EPIC_SECTIONS)
        ]
        for story in _parse_stories(doc, epic.name, graph.root, d):
            _attach_story_md(graph, epic, story)
            epic.stories.append(story)
        graph.epics.append(epic)


def _frontmatter_services(frontmatter: Mapping) -> tuple[str, ...]:
    """A story's `services:` frontmatter list as book names, in file order and without repeats."""
    value = frontmatter.get("services")
    parts = value if isinstance(value, list) else []
    return tuple(dict.fromkeys(str(part).strip() for part in parts if str(part).strip()))


def _attach_story_md(graph: Graph, epic: Epic, story: Story) -> None:
    candidates = []
    if story.path:
        candidates.append(graph.root / story.path)
    candidates.append(epic.directory / "stories" / story.slug / "story.md")
    for c in candidates:
        if c.exists() and c.is_file():
            story.story_md = c
            doc = read_doc(c)
            if doc.frontmatter:
                story.file_eid = str(doc.frontmatter.get("id") or "")
                story.conflict = str(doc.frontmatter.get("conflict") or "").strip()
                story.services = _frontmatter_services(doc.frontmatter)
                story.raw["services"] = list(story.services)
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
