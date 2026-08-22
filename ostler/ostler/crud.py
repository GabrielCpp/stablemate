"""`ostler` mutation — create/delete epics, stories, features; add/remove seeds; set status.

All structural mutation goes through here so id allocation (``ids.py``) and the canonical markdown
layout (``SPEC.md`` / ``registry.py``) stay correct. Writers apply immediately and return a
:class:`Result`; the CLI prints its message.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from ostler import ids, markdown, model, path as path_mod, registry, select, todo as todo_mod
from ostler.model import Graph
from ostler.result import Result   # re-exported: `from ostler.crud import Result` still works


# ---------------------------------------------------------------------------
# markdown section helpers (operate on a MarkdownDoc's body, preserving frontmatter)
# ---------------------------------------------------------------------------
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
    """The body of a story's ``## Dependencies`` section: a bullet each, or the bare ``(none)``.

    The empty tokens are dropped rather than written: `--depends '(none)'` is how a caller says
    "no blockers", and rendering it as `- Blocked by: (none)` would state a blocker named
    `(none)` — the exact bullet the section must never carry.
    """
    slugs = [d.strip() for d in depends if d.strip().lower() not in registry.EMPTY_TOKENS]
    if not slugs:
        return [registry.STORY_DEPS_NONE]
    return [f"- {registry.STORY_DEPS_LABEL}: {slug}" for slug in slugs]


def _write_section_body(doc: markdown.MarkdownDoc, heading: str, body: list[str]) -> bool:
    """Rewrite one ``## heading`` body in a story doc; False when it has no such heading.

    Replaces the section's whole body rather than editing bullets in place: the list is
    ostler's to state, and a stale ``- Blocked by:`` left behind by a shorter new list would be
    read as a real blocker. Refusing when the heading is absent is what keeps a malformed story
    from silently acquiring a second section of the same name.
    """
    section = doc.find_section(heading)
    if section is None:
        return False
    lines = doc.body.split("\n")
    end = section.line_end
    while end > section.line_start + 1 and not lines[end - 1].strip():
        end -= 1                                  # keep the blank line before the next heading
    lines[section.line_start + 1:end] = ["", *body]
    doc.body = "\n".join(lines)
    doc._sections = None
    return True


def _write_dependencies(doc: markdown.MarkdownDoc, depends: list[str]) -> bool:
    """Rewrite a story doc's ``## Dependencies`` body; False when it has no such heading."""
    return _write_section_body(doc, registry.STORY_DEPS_HEADING, _dependency_lines(depends))


def ensure_dependencies(doc: markdown.MarkdownDoc, depends: list[str]) -> None:
    """State *depends* in a story doc's ``## Dependencies``, adding the section when it has none.

    The tolerant form of :func:`_write_dependencies`, for a migration meeting story.md files
    written before the section existed. `update_story` deliberately does *not* use it: there, a
    missing heading means the story is malformed and the operator should hear about it.
    """
    if _write_dependencies(doc, depends):
        return
    lines = doc.body.split("\n")
    # Directly under the H1 — the blockers are the first thing a reader of the story needs.
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
    """State *fixtures* in a story doc's ``## Fixtures``, adding the section when it has none.

    The tolerant form, for a migration meeting story.md files written before the section
    existed. Those stories arranged state anyway — in a block of Python copied into each plan
    that needed it — so the migration writes ``(none)`` and the first `doctor` run over a repo
    with QA plans is what says which names belong there instead.
    """
    if _write_section_body(doc, registry.STORY_FIXTURES_HEADING, _fixture_lines(fixtures)):
        return
    lines = doc.body.split("\n")
    deps = doc.find_section(registry.STORY_DEPS_HEADING)
    # Directly under Dependencies when there is one, so the two machine-stated lists stay
    # together; under the H1 otherwise, which is where Dependencies itself would have gone.
    at = deps.line_end if deps is not None else next(
        (i + 1 for i, ln in enumerate(lines) if ln.startswith("# ")), 0)
    # A section's end already carries whatever blank lines separated it from the next heading;
    # back over them so the insertion owns its own spacing and cannot double it.
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    lines[at:at] = [
        "", f"## {registry.STORY_FIXTURES_HEADING}", "", *_fixture_lines(fixtures), "",
    ]
    doc.body = "\n".join(lines)
    doc._sections = None


def dump_frontmatter(fm: dict) -> str:
    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# milestones
# ---------------------------------------------------------------------------
def create_milestone(
    graph: Graph,
    name: str,
    title: str,
    source_items: list[str] | None = None,
    prefix: str | None = None,
) -> Result:
    """Create a release milestone with a generated id and backlog ownership."""
    path = graph.doc_roots["milestones"] / f"{name}.md"
    if path.exists():
        return Result(False, f"milestone '{name}' already exists")
    eid = ids.allocate(graph, prefix)
    fm = {
        "type": "milestone",
        "id": eid,
        "title": title,
        "status": "planned",
        "dependsOn": [],
        "sourceItems": source_items or [],
        "epics": [],
    }
    text = f"---\n{dump_frontmatter(fm)}---\n# {title}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _set_milestone_epics(milestone: model.Milestone, epics: list[str]) -> None:
    """Replace one milestone's epic membership while preserving its prose and other fields."""
    doc = markdown.split(milestone.path.read_text(encoding="utf-8"))
    fm = dict(doc.frontmatter or {})
    fm["epics"] = epics
    doc.frontmatter = fm
    doc.raw_frontmatter = dump_frontmatter(fm)
    milestone.path.write_text(doc.render(), encoding="utf-8")


# ---------------------------------------------------------------------------
# epics
# ---------------------------------------------------------------------------
def create_epic(graph: Graph, name: str, title: str, prefix: str | None = None) -> Result:
    """Create ``<epics>/NNNN-<slug>/epic.md`` — the epic's directory carries its order.

    The number is minted here and nowhere else, one past the highest already on disk. It
    makes a listing of the epics root read in the order the epics were written, which is
    the order they are meant to be worked; it is not an identity, so every command that
    takes an epic name also accepts the bare slug (:func:`path.epic_dir`). A caller that
    numbered the name itself keeps its number. The name that ended up on disk comes back as
    ``entity_name``, since it is the one the caller must write files under.
    """
    eroot = graph.doc_roots["epics"]
    existing = path_mod.epic_dir(graph, name)
    if (existing / "epic.md").exists():
        return Result(False, f"epic '{existing.name}' already exists")
    dir_name = name if registry.epic_seq(name) is not None else registry.epic_dir_name(
        registry.next_epic_seq(d.name for d in path_mod.epic_dirs(graph)),
        registry.epic_slug(name))
    edir = eroot / dir_name
    epic_md = edir / "epic.md"
    eid = ids.allocate(graph, prefix)
    fm = {"type": "epic", "id": eid, "title": title, "status": "planned"}
    text = f"---\n{dump_frontmatter(fm)}---\n# Epic: {title}\n\n## Seeds\n\n## Stories\n"
    edir.mkdir(parents=True, exist_ok=True)
    epic_md.write_text(text, encoding="utf-8")
    return Result(True, f"created epic '{dir_name}' ({eid})", [epic_md],
                  entity_id=eid, entity_name=dir_name)


def delete_epic(graph: Graph, name: str) -> Result:
    edir = path_mod.epic_dir(graph, name)
    existed = (edir / "epic.md").exists()
    changed: list[Path] = []
    target_refs = {
        name,
        registry.epic_slug(name),
        edir.name,
        registry.epic_slug(edir.name),
    }
    for milestone in graph.milestones:
        remaining = [epic for epic in milestone.epics if epic not in target_refs]
        if remaining != milestone.epics:
            _set_milestone_epics(milestone, remaining)
            changed.append(milestone.path)
    removed = ""
    todo_result = todo_mod.prune(graph, name)
    if todo_result.ok:
        removed = " (removed from epics index)"
        changed.extend(todo_result.paths)
    if edir.exists():
        shutil.rmtree(edir)
    if not existed:
        return Result(
            True,
            f"epic '{name}' already absent; cleanup complete{removed}",
            changed,
            entity_name=name,
        )
    return Result(
        True,
        f"deleted epic '{edir.name}'{removed}",
        [edir, *changed],
        entity_name=edir.name,
    )


# ---------------------------------------------------------------------------
# stories
# ---------------------------------------------------------------------------
def _story_block(slug: str, title: str, sid: str, covers: list[str]) -> list[str]:
    return [
        f"### {slug}",
        f"- title: {title}",
        f"- id: {sid}",
        f"- covers: {', '.join(covers) if covers else '(none)'}",
        "",
    ]


def _story_body(title: str, depends: list[str]) -> str:
    """The story.md skeleton, generated from ``registry.STORY_SECTIONS``.

    Scaffolding from the same table the checks read is the point: a hardcoded skeleton drifts
    into satisfying its own validators, which is how a repo full of empty stories reported
    itself authored. Sections carrying a machine-written field get their `stub`; the `filled`
    ones are left deliberately blank so they read as unwritten until an author writes them.
    """
    lines = [f"# Story: {title}", ""]
    for spec in registry.STORY_SECTIONS:
        lines += [f"## {spec.heading}", ""]
        if spec.heading == registry.STORY_DEPS_HEADING:
            lines += [*_dependency_lines(depends), ""]
        elif spec.stub:
            lines += [spec.stub, ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def create_story(graph: Graph, epic_name: str, slug: str, title: str,
                 covers: list[str] | None = None, depends: list[str] | None = None,
                 prefix: str | None = None) -> Result:
    edir = path_mod.epic_dir(graph, epic_name)
    epic_md = edir / "epic.md"
    if not epic_md.exists():
        return Result(False, f"no epic '{epic_name}'")
    story_md = edir / "stories" / slug / "story.md"
    if story_md.exists():
        # Idempotent on purpose: the author workflow's bounded rework loops re-run
        # `ostler create story`, and `split-stories.md` documents this as a no-op. Keep the
        # existing story body and its already-allocated id untouched — re-allocating would
        # break every reference to it.
        return Result(True, f"story '{slug}' already exists in epic '{epic_name}'", [story_md])

    sid = ids.allocate(graph, prefix)
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    _insert_subsection(doc, registry.STORIES_HEADING,
                       _story_block(slug, title, sid, covers or []))
    epic_md.write_text(doc.render(), encoding="utf-8")

    # The allocated id belongs in the story's own frontmatter, not only in the epic's
    # `## Stories` block. A story.md is read on its own constantly — by the coder workflow
    # picking up work, by `ostler trace`, by a human opening the file — and without the id
    # there is no way to name the story from the file itself; you have to go back to the
    # parent epic and match on slug. Ids are ostler-minted and repo-prefixed (`TODO-15`), so
    # carrying it here is what makes the story addressable in the graph.
    fm = {"type": "story", "id": sid, "slug": slug, "status": registry.DEFAULT_STORY_STATUS}
    body = _story_body(title, depends or [])
    story_md.parent.mkdir(parents=True, exist_ok=True)
    story_md.write_text(f"---\n{dump_frontmatter(fm)}---\n{body}", encoding="utf-8")
    return Result(True, f"created story '{slug}' ({sid}) in epic '{epic_name}'",
                  [epic_md, story_md], entity_id=sid)


def update_story(
    graph: Graph,
    slug: str,
    *,
    title: str,
    covers: list[str],
    depends: list[str],
    fixtures: list[str] | None = None,
) -> Result:
    """Replace a story's graph metadata without touching its id, body, status, or extra fields.

    Two files, because the two edges live where each is readable: `covers` names seeds defined in
    the epic and is rewritten there, while the blockers are rewritten in the story's own
    ``## Dependencies`` section. Both are written or the call fails — a half-applied update would
    leave the DAG stating one thing in one file and another in the other.

    *fixtures* is optional and rewritten tolerantly, because unlike the other two it is not known
    when a story is created: which arrangements a story needs is settled by its QA plan, which is
    written much later. ``None`` leaves the section alone; a list — including the empty one —
    states it, adding the section to a story.md written before the contract required it.
    """
    found = graph.find_story(slug)
    if found is None:
        return Result(False, f"no story '{slug}'")
    epic, story = found
    epic_md = epic.epic_md
    if epic_md is None:
        return Result(False, f"epic '{epic.name}' has no epic.md to update the story in")

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


def delete_story(graph: Graph, slug: str) -> Result:
    found = graph.find_story(slug)
    if found is None:
        return Result(False, f"no story '{slug}'")
    epic, story = found
    epic_md = epic.epic_md
    if epic_md is None:
        return Result(False, f"epic '{epic.name}' has no epic.md to remove the story from")
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    _remove_subsection(doc, registry.STORIES_HEADING, slug)
    epic_md.write_text(doc.render(), encoding="utf-8")
    if story.story_md and story.story_md.exists():
        shutil.rmtree(story.story_md.parent)
    return Result(True, f"deleted story '{slug}' from epic '{epic.name}'", [epic_md])


def set_status(graph: Graph, slug: str, status: str) -> Result:
    found = graph.find_story(slug)
    if found is None or found[1].story_md is None:
        return Result(False, f"no story '{slug}' with a story.md")
    path = found[1].story_md
    doc = markdown.split(path.read_text(encoding="utf-8"))
    fm = doc.frontmatter or {"type": "story", "slug": slug}
    fm["status"] = status
    doc.raw_frontmatter = dump_frontmatter(fm)
    # Rewrite the body's `- **Status**:` bullet in place, located through the parsed tree rather
    # than by matching the rendered text: only the real field is touched, and its indentation,
    # list marker and emphasis survive verbatim.
    bullet = model.status_bullet(doc)
    if bullet is not None:
        lines = doc.body.split("\n")
        head, sep, _ = lines[bullet.line_start].partition(":")
        if sep:
            lines[bullet.line_start] = f"{head}: {status}"
            doc.replace_body(lines)
    path.write_text(doc.render(), encoding="utf-8")
    return Result(True, f"status of '{slug}' → {status}", [path])


def unblock(graph: Graph, *, story: str = "", epic: str = "",
            status: str = registry.DEFAULT_STORY_STATUS) -> Result:
    """Clear the give-up stamp off a story, an epic's stories, or the whole graph.

    The coder workflow no longer stamps these — a give-up ends the run instead — but every
    story stamped by a run that predates that still carries one, and `Blocked` is still
    written by hand. The reason this is a command rather than an operator editing
    frontmatter: the stamp is a *sentence* (``QA
    give-up after 4 attempts — needs manual review: docs/specs/11-copy-link/qa.md``), it is
    written into two places in every story.md (the frontmatter field and the body bullet),
    and a run gives up on several stories at once — six in one observed epic, all of which an
    operator then had to find and retype identically. `set_status` can do one of them if you
    already know the slug and the exact replacement; this knows which stories are stamped.

    Only a story :func:`select.is_blocked` reads as blocked is rewritten. A done story is
    never touched — the vocabulary check would let ``QA passed`` through no more than it lets
    ``Not started`` through, and silently resetting finished work is the one failure this
    must not have. Which makes it idempotent: unblocking twice writes nothing the second
    time and still succeeds, so a script can run it unconditionally.

    Scope is exactly one of `story` / `epic` / neither (the whole graph); the CLI is what
    refuses an accidental sweep, by making the graph-wide form ask for ``--all``.
    """
    if story and epic:
        return Result(False, "pass a story or an epic, not both")

    if story:
        found = graph.find_story(story)
        if found is None:
            return Result(False, f"no story '{story}'")
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
        res = set_status(graph, candidate.slug, status)
        if res.ok:
            cleared.append(candidate.slug)
            paths.extend(res.paths)
        else:
            failures.append(f"{candidate.slug} ({res.message})")

    message = f"unblocked {len(cleared)} → {status}: {', '.join(cleared)}" if cleared else ""
    if failures:
        # Partial success is still a write, so the paths already rewritten are reported —
        # a caller that commits `res.paths` must not lose them to an unrelated story's
        # missing story.md.
        message = (message + "; " if message else "") + f"could not unblock {', '.join(failures)}"
        return Result(False, message, paths)
    return Result(True, message, paths)


# ---------------------------------------------------------------------------
# seeds (live in epic.md `## Seeds`)
# ---------------------------------------------------------------------------
def _tags(value: object) -> list[str]:
    """A list-valued seed meta argument as normalized tags, from a list or a comma string.

    Callers reach `add_seed` from both the CLI (`--layer` repeated → a list) and Python
    (a comma-joined string), and the seed block stores one spelling, so normalize here.
    """
    parts = value if isinstance(value, (list, tuple)) else [value]
    tags: list[str] = []
    for part in parts:
        # Split inside each part too: `--layer frontend,backend` is the spelling an agent
        # reaches for even when the flag is repeatable, and it should mean the same thing.
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
    # `layers` is a closed vocabulary because the author's mockup gate branches on it: an
    # unrecognized token would read as "not frontend" and silently skip a design turn, which
    # is exactly the class of failure the gate exists to prevent. Reject it at write time.
    bad = [t for t in _tags((meta or {}).get("layers")) if t not in registry.SEED_LAYERS]
    if bad:
        return Result(False, f"invalid layer{'s' if len(bad) > 1 else ''} "
                             f"'{', '.join(bad)}' (one of {', '.join(registry.SEED_LAYERS)})")
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    sec = doc.find_section(registry.SEEDS_HEADING)
    # Update-or-create: `write-epic.md` documents re-running this as updating the seed rather
    # than duplicating it, and the author's bounded rework loops depend on that. The block is
    # fully regenerated from the arguments, so an update is a replace.
    existed = sec is not None and any(c.title.strip() == seed_id for c in sec.children)
    if existed:
        _remove_subsection(doc, registry.SEEDS_HEADING, seed_id)
    block = [f"### {seed_id}", f"- status: {status}"]
    for key in ("surface", "legacySurface", "backing", "prerequisites", "sourceBullet",
                "layers", "services"):
        val = (meta or {}).get(key)
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


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------
def create_feature(graph: Graph, slug: str, title: str, area: str = "",
                   route: str = "", prefix: str | None = None) -> Result:
    froot = graph.doc_roots["features"]
    path = (froot / area / f"{slug}.md") if area else (froot / f"{slug}.md")
    if path.exists():
        return Result(False, f"feature '{slug}' already exists")
    fid = ids.allocate(graph, prefix)
    fm = {"type": "feature", "id": fid, "slug": slug, "title": title}
    if area:
        fm["area"] = area
    if route:
        fm["route"] = route
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dump_frontmatter(fm)}---\n# {title}\n\n", encoding="utf-8")
    return Result(True, f"created feature '{slug}' ({fid})", [path], entity_id=fid)


def create_spec(specs_root: Path, slug: str, doc: str, title: str = "") -> Result:
    """Create — or retro-stamp — a coder process artifact at ``docs/specs/<slug>/<doc>``.

    Idempotent on purpose: the coder writes these docs as free-form markdown, so this has to be
    callable *after* the write as well as before it. An existing file keeps its body and gains only
    the ``type`` it was missing; an already-typed file is left completely alone. No id is allocated
    — a spec is a process artifact, not a graph node (``registry`` requires only ``type``).

    Takes the specs *root*, not a ``Graph``, and it is the only mutation here that does. It reads
    no node, resolves no id and consults no other document — the graph was only ever a way to
    spell one configured directory. Asking for it cost a full parse of every markdown file in the
    book: twenty-four seconds on a real one, paid once per file by the coder's ``stamp_specs``,
    which runs after every writer phase. ``ostler.path.specs_root_in`` derives the same directory
    from config alone.
    """
    name = doc if doc.endswith(".md") else f"{doc}.md"
    if "/" in slug or "/" in doc:
        return Result(False, f"spec slug/doc must be single path segments, got '{slug}/{doc}'")
    if name in registry.RESERVED_FILES:
        return Result(False, f"'{name}' is a reserved file, not a spec Concept")
    path = specs_root / slug / name
    type_value = registry.spec_type_for(name)
    if path.exists():
        mdoc = markdown.split(path.read_text(encoding="utf-8"))
        fm = (mdoc.frontmatter or {}) if mdoc.has_frontmatter else {}
        declared = registry.type_of(fm)
        if declared:
            return Result(True, f"spec '{slug}/{name}' already typed ({declared})", [path])
        fm.pop("type", None)   # a present-but-blank `type:` must not shadow the stamp
        path.write_text(f"---\n{dump_frontmatter({'type': type_value, **fm})}---\n{mdoc.body}",
                        encoding="utf-8")
        return Result(True, f"stamped spec '{slug}/{name}' ({type_value})", [path])
    body = f"# {title}\n\n" if title else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dump_frontmatter({'type': type_value})}---\n{body}", encoding="utf-8")
    return Result(True, f"created spec '{slug}/{name}' ({type_value})", [path])


def delete_feature(graph: Graph, slug: str) -> Result:
    for feat in graph.features:
        if feat.slug == slug:
            feat.path.unlink()
            return Result(True, f"deleted feature '{slug}'", [feat.path])
    return Result(False, f"no feature '{slug}'")
