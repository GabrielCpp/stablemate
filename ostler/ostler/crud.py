"""`ostler` mutation — create/delete epics, stories, features; add/remove seeds; set status."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from ostler import ids, markdown, milestones as milestones_mod, model, path as path_mod, registry, select
from ostler.model import Epic, Graph, Story
from ostler.result import Result


def _insert_subsection(doc: markdown.MarkdownDoc, heading: str, block: list[str]) -> None:
    """Insert a ``### …`` *block* under the ``## heading`` section, creating it if absent."""
    body_lines = doc.body.split("\n")
    sec = doc.find_section(heading)
    if sec is None:
        out = list(body_lines)
        while out and out[-1].strip() == "":
            out.pop()
        out += ["", f"## {heading}", "", *block]
        doc.body = "\n".join(out) + "\n"
    else:
        at = sec.line_end
        doc.body = "\n".join(body_lines[:at] + block + body_lines[at:])
    doc._sections = None


def _remove_subsection(doc: markdown.MarkdownDoc, heading: str, sub_title: str) -> bool:
    sec = doc.find_section(heading)
    if sec is None:
        return False
    for child in sec.children:
        if child.title.strip() == sub_title:
            body_lines = doc.body.split("\n")
            del body_lines[child.line_start:child.line_end]
            doc.body = "\n".join(body_lines)
            doc._sections = None
            return True
    return False


def _dependency_lines(depends: list[str]) -> list[str]:
    """The body of a story's ``## Dependencies`` section: a bullet each, or the bare ``(none)``."""
    slugs = [d.strip() for d in depends if d.strip().lower() not in registry.EMPTY_TOKENS]
    if not slugs:
        return [registry.STORY_DEPS_NONE]
    return [f"- {registry.STORY_DEPS_LABEL}: {slug}" for slug in slugs]


def _write_section_body(doc: markdown.MarkdownDoc, heading: str, body: list[str]) -> bool:
    """Rewrite one ``## heading`` body in a story doc; False when it has no such heading."""
    section = doc.find_section(heading)
    if section is None:
        return False
    lines = doc.body.split("\n")
    end = section.line_end
    if end < len(lines):
        lines[section.line_start + 1:end] = ["", *body, ""]
    else:
        while end > section.line_start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[section.line_start + 1:end] = ["", *body]
    doc.body = "\n".join(lines)
    doc._sections = None
    return True


def _write_dependencies(doc: markdown.MarkdownDoc, depends: list[str]) -> bool:
    """Rewrite a story doc's ``## Dependencies`` body; False when it has no such heading."""
    return _write_section_body(doc, registry.STORY_DEPS_HEADING, _dependency_lines(depends))


def ensure_dependencies(doc: markdown.MarkdownDoc, depends: list[str]) -> None:
    """State *depends* in a story doc's ``## Dependencies``, adding the section when it has none."""
    if _write_dependencies(doc, depends):
        return
    lines = doc.body.split("\n")
    after_title = next((i + 1 for i, ln in enumerate(lines) if ln.startswith("# ")), 0)
    lines[after_title:after_title] = [
        "", f"## {registry.STORY_DEPS_HEADING}", "", *_dependency_lines(depends),
    ]
    doc.body = "\n".join(lines)
    doc._sections = None


def _fixture_lines(fixtures: list[str]) -> list[str]:
    """The body of a story's ``## Fixtures`` section: a bullet each, or the bare ``(none)``."""
    names = [n.strip() for n in fixtures if n.strip().lower() not in registry.EMPTY_TOKENS]
    if not names:
        return [registry.STORY_FIXTURES_NONE]
    return [f"- {registry.STORY_FIXTURES_LABEL}: {name}" for name in names]


def ensure_fixtures(doc: markdown.MarkdownDoc, fixtures: list[str]) -> None:
    """State *fixtures* in a story doc's ``## Fixtures``, adding the section when it has none."""
    if _write_section_body(doc, registry.STORY_FIXTURES_HEADING, _fixture_lines(fixtures)):
        return
    lines = doc.body.split("\n")
    deps = doc.find_section(registry.STORY_DEPS_HEADING)
    at = deps.line_end if deps is not None else next(
        (i + 1 for i, ln in enumerate(lines) if ln.startswith("# ")), 0)
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    lines[at:at] = [
        "", f"## {registry.STORY_FIXTURES_HEADING}", "", *_fixture_lines(fixtures), "",
    ]
    doc.body = "\n".join(lines)
    doc._sections = None


def dump_frontmatter(fm: dict) -> str:
    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)


def create_milestone(
    graph: Graph,
    name: str,
    title: str,
    source_items: list[str] | None = None,
) -> Result:
    """Create ``<milestones>/NNNN-<slug>/milestone.md`` with a generated id; the folder's number carries its order."""
    mroot = graph.doc_roots["milestones"]
    if mroot.parent.name == "-":
        return Result(False, "run from the code repository the milestone is for (`ostler -C <repo>`)")
    existing = graph.milestone_by_name(name)
    if existing is not None:
        return Result(False, f"milestone '{existing.name}' already exists")
    if registry.epic_seq(name) is None:
        taken = [d.name for d in mroot.iterdir() if d.is_dir()] if mroot.is_dir() else []
        name = registry.epic_dir_name(registry.next_epic_seq(taken), name)
    folder = mroot / name
    path = folder / registry.MILESTONE_FILE
    if folder.exists():
        return Result(False, f"milestone '{name}' already exists")
    eid = ids.allocate(graph)
    fm = {
        "type": "milestone",
        "id": eid,
        "title": title,
        "status": registry.MILESTONE_DEFAULT_STATUS,
        "dependsOn": [],
        "sourceItems": source_items or [],
        "epics": [],
    }
    stubs = "".join(f"\n## {spec.heading}\n" for spec in registry.MILESTONE_SECTIONS)
    text = f"---\n{dump_frontmatter(fm)}---\n# {title}\n{stubs}"
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return Result(
        True,
        f"created milestone '{name}' ({eid})",
        [path],
        entity_id=eid,
        entity_name=name,
    )


def set_milestone_source_items(
    graph: Graph,
    name: str,
    source_items: list[str],
) -> Result:
    """Replace a milestone's owned backlog ids while preserving its prose."""
    milestone = graph.milestone_by_name(name)
    if milestone is None:
        return Result(False, f"no milestone '{name}'")
    doc = markdown.split(milestone.path.read_text(encoding="utf-8"))
    fm = dict(doc.frontmatter or {})
    fm["sourceItems"] = source_items
    doc.frontmatter = fm
    doc.raw_frontmatter = dump_frontmatter(fm)
    milestone.path.write_text(doc.render(), encoding="utf-8")
    return Result(
        True,
        f"set {len(source_items)} source item(s) on milestone '{milestone.name}'",
        [milestone.path],
        entity_id=milestone.eid,
        entity_name=milestone.name,
    )


def _write_milestone_epics(graph: Graph, milestone: model.Milestone, epics: list[Epic]) -> None:
    """Make *epics* the milestone's epic list: their ids under `epics:` and the `## Epics` section a reader sees."""
    milestone.epic_refs = [epic.eid for epic in epics]
    milestone.epics = [epic.name for epic in epics]
    doc = markdown.split(milestone.path.read_text(encoding="utf-8"))
    fm = dict(doc.frontmatter or {})
    fm["epics"] = milestone.epic_refs
    doc.frontmatter = fm
    doc.raw_frontmatter = dump_frontmatter(fm)
    body = milestones_mod.epics_section_lines(graph, milestone)
    if not _write_section_body(doc, registry.MILESTONE_EPICS_HEADING, body):
        lines = doc.body.split("\n")
        at = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
        lines[at:at] = [f"## {registry.MILESTONE_EPICS_HEADING}", "", *body, ""]
        doc.body = "\n".join(lines)
        doc._sections = None
    milestone.path.write_text(doc.render(), encoding="utf-8")


def set_milestone_epics(graph: Graph, name: str, refs: list[str] | None = None) -> Result:
    """Set a milestone's epics in coding order, each named by id, directory or slug, and stored by id.

    With no *refs* the milestone's own list is resolved again, which moves a list written by name
    onto ids and rewrites its `## Epics` section.
    """
    milestone = graph.milestone_by_name(name)
    if milestone is None:
        return Result(False, f"no milestone '{name}'")
    wanted = milestone.epic_refs if refs is None else refs
    epics: list[Epic] = []
    errors: list[str] = []
    for ref in wanted:
        epic = graph.epic_by_ref(ref)
        if epic is None:
            errors.append(f"'{ref}' names no epic")
        elif not epic.eid:
            errors.append(f"epic '{epic.name}' has no `id:`, so a milestone cannot list it")
        elif epic in epics:
            errors.append(f"epic '{epic.name}' is listed twice")
        else:
            epics.append(epic)
    if errors:
        return Result(False, f"milestone '{milestone.name}' keeps its epics: " + "; ".join(errors))
    _write_milestone_epics(graph, milestone, epics)
    return Result(
        True,
        f"set {len(epics)} epic(s) on milestone '{milestone.name}'",
        [milestone.path],
        entity_id=milestone.eid,
        entity_name=milestone.name,
    )


def create_epic(
    graph: Graph,
    name: str,
    title: str,
    *,
    followups: bool = False,
) -> Result:
    """Create ``<epics>/<epic-id>/epic.md``; the slug *name* names it in commands and branches."""
    slug = registry.epic_slug(name)
    existing = graph.epic_by_ref(slug)
    if existing is not None:
        return Result(False, f"epic '{slug}' already exists ({existing.name})")
    eid = ids.allocate(graph)
    edir = graph.doc_roots["epics"] / eid
    epic_md = edir / "epic.md"
    fm: dict[str, object] = {"type": "epic", "id": eid, "slug": slug, "title": title,
                             "status": "planned"}
    if followups:
        fm["followups"] = True
    text = f"---\n{dump_frontmatter(fm)}---\n# Epic: {title}\n\n## Seeds\n\n## Stories\n"
    edir.mkdir(parents=True, exist_ok=True)
    epic_md.write_text(text, encoding="utf-8")
    return Result(True, f"created epic '{slug}' ({eid})", [epic_md],
                  entity_id=eid, entity_name=eid)


def delete_epic(graph: Graph, name: str) -> Result:
    edir = path_mod.epic_dir(graph, name)
    existed = (edir / "epic.md").exists()
    changed: list[Path] = []
    for milestone in graph.milestones:
        if edir.name not in milestone.epics:
            continue
        remaining = [graph.epic_by_ref(ref) for ref in milestone.epic_refs]
        _write_milestone_epics(graph, milestone, [
            epic for epic in remaining
            if epic is not None and epic.eid and epic.name != edir.name])
        changed.append(milestone.path)
    if edir.exists():
        shutil.rmtree(edir)
    if not existed:
        return Result(
            True,
            f"epic '{name}' already absent; cleanup complete",
            changed,
            entity_name=name,
        )
    return Result(
        True,
        f"deleted epic '{edir.name}'",
        [edir, *changed],
        entity_name=edir.name,
    )


def _story_block(slug: str, title: str, sid: str, covers: list[str]) -> list[str]:
    return [
        f"### {slug}",
        f"- title: {title}",
        f"- id: {sid}",
        f"- covers: {', '.join(covers) if covers else '(none)'}",
        "",
    ]


def _story_body(title: str, depends: list[str]) -> str:
    """The story.md skeleton, generated from ``registry.STORY_SECTIONS``."""
    lines = [f"# Story: {title}", ""]
    for spec in registry.STORY_SECTIONS:
        lines += [f"## {spec.heading}", ""]
        if spec.heading == registry.STORY_DEPS_HEADING:
            lines += [*_dependency_lines(depends), ""]
        elif spec.stub:
            lines += [spec.stub, ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def create_story(graph: Graph, epic_name: str, slug: str, title: str,
                 covers: list[str] | None = None, depends: list[str] | None = None) -> Result:
    epic = graph.epic_by_ref(epic_name)
    if epic is None or epic.epic_md is None:
        return Result(False, f"no epic '{epic_name}'")
    epic_md = epic.epic_md
    same = next((s for s in epic.stories if s.slug == slug), None)
    if same is not None:
        return Result(True, f"story '{slug}' already exists in epic '{epic_name}'",
                      [same.story_md] if same.story_md else [])

    sid = ids.allocate(graph)
    story_md = epic.directory / "stories" / sid / "story.md"
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    _insert_subsection(doc, registry.STORIES_HEADING,
                       _story_block(slug, title, sid, covers or []))
    epic_md.write_text(doc.render(), encoding="utf-8")

    fm = {
        "type": "story",
        "id": sid,
        "slug": slug,
        "status": registry.DEFAULT_STORY_STATUS,
    }
    body = _story_body(title, depends or [])
    story_md.parent.mkdir(parents=True, exist_ok=True)
    story_md.write_text(f"---\n{dump_frontmatter(fm)}---\n{body}", encoding="utf-8")
    return Result(True, f"created story '{slug}' ({sid}) in epic '{epic_name}'",
                  [epic_md, story_md], entity_id=sid)


def _story_in_epic(graph: Graph, slug: str, purpose: str) -> tuple[Epic, Story, Path] | Result:
    """The epic, story and epic.md of *slug*, or the refusal naming what *purpose* lacks."""
    found = graph.find_story(slug)
    if found is None:
        return Result(False, graph.no_story(slug))
    epic, story = found
    if epic.epic_md is None:
        return Result(False, f"epic '{epic.name}' has no epic.md to {purpose}")
    return epic, story, epic.epic_md


def _story_page(graph: Graph, slug: str) -> tuple[Path, markdown.MarkdownDoc, dict] | Result:
    """The story.md of *slug*, parsed, with its frontmatter, or why it has none."""
    found = graph.find_story(slug)
    if found is None:
        return Result(False, graph.no_story(slug))
    story = found[1]
    if story.story_md is None:
        return Result(False, f"story '{story.slug}' has no story.md")
    doc = markdown.split(story.story_md.read_text(encoding="utf-8"))
    return story.story_md, doc, doc.frontmatter or {"type": "story", "slug": slug}


def update_story(
    graph: Graph,
    slug: str,
    *,
    title: str,
    covers: list[str],
    depends: list[str],
    fixtures: list[str] | None = None,
) -> Result:
    """Replace a story's graph metadata without touching its id, body, status, or extra fields."""
    located = _story_in_epic(graph, slug, "update the story in")
    if isinstance(located, Result):
        return located
    epic, story, epic_md = located
    slug = story.slug

    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    section = doc.find_section(registry.STORIES_HEADING)
    story_section = next(
        (child for child in section.children if child.title.strip() == slug),
        None,
    ) if section is not None else None
    if story_section is None:
        return Result(False, f"no story '{slug}'")

    story_md = story.story_md
    if story_md is None:
        return Result(False, f"story '{slug}' has no story.md to write its dependencies into")
    story_doc = markdown.split(story_md.read_text(encoding="utf-8"))
    if not _write_dependencies(story_doc, depends):
        return Result(
            False,
            f"story '{slug}' has no '## {registry.STORY_DEPS_HEADING}' section to update",
        )
    if fixtures is not None:
        ensure_fixtures(story_doc, fixtures)

    values = {
        "title": title,
        registry.STORY_COVERS_KEY: ", ".join(covers) if covers else "(none)",
    }
    lines = doc.body.split("\n")
    seen: set[str] = set()
    for bullet in story_section.bullets:
        if bullet.label not in values:
            continue
        head, sep, _old = lines[bullet.line_start].partition(":")
        if sep:
            lines[bullet.line_start] = f"{head}: {values[bullet.label]}"
            seen.add(bullet.label)
    if missing := [label for label in values if label not in seen]:
        return Result(False, f"story '{slug}' is missing metadata: {', '.join(missing)}")
    doc.replace_body(lines)
    epic_md.write_text(doc.render(), encoding="utf-8")
    story_md.write_text(story_doc.render(), encoding="utf-8")
    return Result(True, f"updated story '{slug}' in epic '{epic.name}'", [epic_md, story_md])


def sync_story_fixtures(graph: Graph, slug: str, names: set[str]) -> Result:
    """Make a story's ``## Fixtures`` state exactly *names*, the fixtures its plan uses."""
    found = graph.find_story(slug)
    if found is None:
        return Result(False, graph.no_story(slug))
    story = found[1]
    story_md = story.story_md
    if story_md is None:
        return Result(False, f"story '{story.slug}' has no story.md to state its fixtures in")
    doc = markdown.split(story_md.read_text(encoding="utf-8"))
    if (
        doc.find_section(registry.STORY_FIXTURES_HEADING) is not None
        and set(story.fixtures) == names
        and not story.fixture_strays
    ):
        return Result(True, f"story '{story.slug}' already states its plan's fixtures")
    ensure_fixtures(doc, sorted(names))
    story_md.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"stated {len(names)} fixture(s) on story '{story.slug}'", [story_md])


def scaffold_missing_sections(graph: Graph, slug: str) -> Result:
    """Give one story every ``registry.STORY_SECTIONS`` heading it lacks, in the table's order."""
    found = graph.find_story(slug)
    if found is None:
        return Result(False, graph.no_story(slug))
    path = found[1].story_md
    if path is None:
        return Result(False, f"no story '{slug}' with a story.md")
    doc = markdown.split(path.read_text(encoding="utf-8"))

    added: list[str] = []
    for position, spec in enumerate(registry.STORY_SECTIONS):
        if doc.find_section(spec.heading) is not None:
            continue
        block = [f"## {spec.heading}", ""]
        if spec.stub:
            block += [spec.stub, ""]
        lines = doc.body.split("\n")
        at = _insert_at(doc, position)
        doc.replace_body(lines[:at] + block + lines[at:])
        added.append(spec.heading)

    if not added:
        return Result(True, f"story '{slug}' already has every required section")
    path.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"added {len(added)} section(s) to story '{slug}': "
                        f"{', '.join(added)}", [path])


def _insert_at(doc: markdown.MarkdownDoc, position: int) -> int:
    """The body line a ``STORY_SECTIONS[position]`` heading belongs on, in this document."""
    for spec in registry.STORY_SECTIONS[position + 1:]:
        section = doc.find_section(spec.heading)
        if section is not None:
            return section.line_start
    return len(doc.body.split("\n"))


def delete_story(graph: Graph, slug: str) -> Result:
    located = _story_in_epic(graph, slug, "remove the story from")
    if isinstance(located, Result):
        return located
    epic, story, epic_md = located
    slug = story.slug
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    _remove_subsection(doc, registry.STORIES_HEADING, slug)
    epic_md.write_text(doc.render(), encoding="utf-8")
    if story.story_md and story.story_md.exists():
        shutil.rmtree(story.story_md.parent)
    return Result(True, f"deleted story '{slug}' from epic '{epic.name}'", [epic_md])


def set_status(graph: Graph, slug: str, status: str) -> Result:
    located = _story_page(graph, slug)
    if isinstance(located, Result):
        return located
    path, doc, fm = located
    text = status.strip()
    if not text:
        return Result(False, f"status of '{slug}' cannot be empty")
    fm["status"] = text
    doc.raw_frontmatter = dump_frontmatter(fm)
    bullet = model.status_bullet(doc)
    if bullet is not None:
        lines = doc.body.split("\n")
        head, sep, _ = lines[bullet.line_start].partition(":")
        if sep:
            lines[bullet.line_start] = f"{head}: {text}"
            doc.replace_body(lines)
    path.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"status of '{slug}' → {text}", [path])


def set_conflict(graph: Graph, slug: str, conflict: str) -> Result:
    """Record, or clear, a story's acceptance-criteria conflict (frontmatter ``conflict:``)."""
    located = _story_page(graph, slug)
    if isinstance(located, Result):
        return located
    path, doc, fm = located
    text = " ".join(conflict.split())
    if text:
        fm["conflict"] = text
    else:
        fm.pop("conflict", None)
    doc.frontmatter = fm
    doc.raw_frontmatter = dump_frontmatter(fm)
    path.write_text(doc.render(), encoding="utf-8")
    verb = "conflict recorded on" if text else "conflict cleared off"
    return Result(True, f"{verb} '{slug}'", [path])


def unblock(graph: Graph, *, story: str = "", epic: str = "",
            status: str = registry.DEFAULT_STORY_STATUS) -> Result:
    """Clear the give-up stamp off a story, an epic's stories, or the whole graph."""
    if story and epic:
        return Result(False, "pass a story or an epic, not both")

    if story:
        found = graph.find_story(story)
        if found is None:
            return Result(False, graph.no_story(story))
        candidates = [found[1]]
    elif epic:
        found_epic = select.epic_by_name(graph, epic)
        if found_epic is None:
            return Result(False, f"no epic '{epic}'")
        candidates = list(found_epic.stories)
    else:
        candidates = [s for e in graph.epics for s in e.stories]

    blocked = [s for s in candidates if select.is_blocked(s.status)]
    if not blocked:
        return Result(True, "nothing to unblock" + (f": '{story or epic}' is not blocked"
                                                    if story or epic else ""))

    paths: list[Path] = []
    cleared: list[str] = []
    failures: list[str] = []
    for candidate in blocked:
        if not candidate.eid:
            failures.append(f"{candidate.slug} (has no story id)")
            continue
        res = set_status(graph, candidate.eid, status)
        if res.ok:
            cleared.append(candidate.slug)
            paths.extend(res.paths)
        else:
            failures.append(f"{candidate.slug} ({res.message})")

    message = f"unblocked {len(cleared)} → {status}: {', '.join(cleared)}" if cleared else ""
    if failures:
        message = (message + "; " if message else "") + f"could not unblock {', '.join(failures)}"
        return Result(False, message, paths)
    return Result(True, message, paths)


def _tags(value: object) -> list[str]:
    """A list-valued seed meta argument as normalized tags, from a list or a comma string."""
    parts = value if isinstance(value, (list, tuple)) else [value]
    tags: list[str] = []
    for part in parts:
        for piece in str(part or "").split(","):
            tag = piece.strip().lower()
            if tag and tag not in tags:
                tags.append(tag)
    return tags


def add_seed(graph: Graph, epic_name: str, seed_id: str, status: str = registry.DEFAULT_SEED_STATUS,
             summary: str = "", meta: dict | None = None) -> Result:
    edir = path_mod.epic_dir(graph, epic_name)
    epic_md = edir / "epic.md"
    if not epic_md.exists():
        return Result(False, f"no epic '{epic_name}'")
    if status not in registry.SEED_STATUSES:
        return Result(False, f"invalid status '{status}' (one of {', '.join(registry.SEED_STATUSES)})")
    bad = [t for t in _tags((meta or {}).get("layers")) if t not in registry.SEED_LAYERS]
    if bad:
        return Result(False, f"invalid layer{'s' if len(bad) > 1 else ''} "
                             f"'{', '.join(bad)}' (one of {', '.join(registry.SEED_LAYERS)})")
    design = str((meta or {}).get("design") or "").strip().lower()
    if design and design not in registry.SEED_DESIGNS:
        return Result(False, f"invalid design '{design}' "
                             f"(one of {', '.join(registry.SEED_DESIGNS)})")
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    sec = doc.find_section(registry.SEEDS_HEADING)
    existed = sec is not None and any(c.title.strip() == seed_id for c in sec.children)
    if existed:
        _remove_subsection(doc, registry.SEEDS_HEADING, seed_id)
    block = [f"### {seed_id}", f"- status: {status}"]
    for key in ("surface", "legacySurface", "backing", "prerequisites", "sourceRecord",
                "layers", "services", "design"):
        val = (meta or {}).get(key)
        if key == "design" and val:
            val = str(val).strip().lower()
        if key in registry.SEED_LIST_META_KEYS:
            val = ", ".join(_tags(val))
        if val:
            block.append(f"- {key}: {val}")
    block.append("")
    if summary:
        block += [summary, ""]
    _insert_subsection(doc, registry.SEEDS_HEADING, block)
    epic_md.write_text(doc.render(), encoding="utf-8")
    verb = "updated" if existed else "added"
    return Result(True, f"{verb} seed '{seed_id}' in epic '{epic_name}'", [epic_md])


def remove_seed(graph: Graph, epic_name: str, seed_id: str) -> Result:
    edir = path_mod.epic_dir(graph, epic_name)
    epic_md = edir / "epic.md"
    if not epic_md.exists():
        return Result(False, f"no epic '{epic_name}'")
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    if not _remove_subsection(doc, registry.SEEDS_HEADING, seed_id):
        return Result(False, f"no seed '{seed_id}' in '{epic_name}'")
    epic_md.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"removed seed '{seed_id}' from epic '{epic_name}'", [epic_md])


def create_spec(specs_root: Path, story: str, doc: str, title: str = "") -> Result:
    """Create — or retro-stamp — a coder process artifact in the story's spec folder, ``<story id>/<doc>``."""
    name = doc if doc.endswith(".md") else f"{doc}.md"
    if "/" in story or "/" in doc:
        return Result(False, f"spec story/doc must be single path segments, got '{story}/{doc}'")
    if name in registry.RESERVED_FILES:
        return Result(False, f"'{name}' is a reserved file, not a spec Concept")
    path = specs_root / story / name
    type_value = registry.spec_type_for(name)
    if path.exists():
        mdoc = markdown.split(path.read_text(encoding="utf-8"))
        fm = (mdoc.frontmatter or {}) if mdoc.has_frontmatter else {}
        declared = registry.type_of(fm)
        if declared:
            return Result(True, f"spec '{story}/{name}' already typed ({declared})", [path])
        fm.pop("type", None)
        path.write_text(f"---\n{dump_frontmatter({'type': type_value, **fm})}---\n{mdoc.body}",
                        encoding="utf-8")
        return Result(True, f"stamped spec '{story}/{name}' ({type_value})", [path])
    body = f"# {title}\n\n" if title else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dump_frontmatter({'type': type_value})}---\n{body}", encoding="utf-8")
    return Result(True, f"created spec '{story}/{name}' ({type_value})", [path])

