"""`ostler` mutation — create/delete epics, stories, features; add/remove seeds; set status.

All structural mutation goes through here so id allocation (``ids.py``) and the canonical markdown
layout (``SPEC.md`` / ``registry.py``) stay correct. Writers apply immediately and return a
:class:`Result`; the CLI prints its message.
"""

from __future__ import annotations

import shutil

import yaml

from ostler import ids, markdown, model, path as path_mod, registry, todo as todo_mod
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


def dump_frontmatter(fm: dict) -> str:
    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)


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
    if not (edir / "epic.md").exists():
        return Result(False, f"no epic '{name}'")
    shutil.rmtree(edir)
    removed = ""
    if todo_mod.prune(graph, edir.name).ok:
        removed = " (removed from epics index)"
    return Result(True, f"deleted epic '{edir.name}'{removed}", [edir], entity_name=edir.name)


# ---------------------------------------------------------------------------
# stories
# ---------------------------------------------------------------------------
def _story_block(slug: str, title: str, sid: str,
                 covers: list[str], depends: list[str]) -> list[str]:
    return [
        f"### {slug}",
        f"- title: {title}",
        f"- id: {sid}",
        f"- covers: {', '.join(covers) if covers else '(none)'}",
        f"- depends on: {', '.join(depends) if depends else '(none)'}",
        "",
    ]


def _story_body(title: str) -> str:
    """The story.md skeleton, generated from ``registry.STORY_SECTIONS``.

    Scaffolding from the same table the checks read is the point: a hardcoded skeleton drifts
    into satisfying its own validators, which is how a repo full of empty stories reported
    itself authored. Only the status section gets a stub line — the `filled` ones are left
    deliberately blank so they read as unwritten until an author writes them.
    """
    lines = [f"# Story: {title}", ""]
    for spec in registry.STORY_SECTIONS:
        lines += [f"## {spec.heading}", ""]
        if spec.heading == registry.STORY_STATUS_HEADING:
            lines += [f"- **{registry.STORY_STATUS_LABEL}**: {registry.DEFAULT_STORY_STATUS}", ""]
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
                       _story_block(slug, title, sid, covers or [], depends or []))
    epic_md.write_text(doc.render(), encoding="utf-8")

    # The allocated id belongs in the story's own frontmatter, not only in the epic's
    # `## Stories` block. A story.md is read on its own constantly — by the coder workflow
    # picking up work, by `ostler trace`, by a human opening the file — and without the id
    # there is no way to name the story from the file itself; you have to go back to the
    # parent epic and match on slug. Ids are ostler-minted and repo-prefixed (`TODO-15`), so
    # carrying it here is what makes the story addressable in the graph.
    fm = {"type": "story", "id": sid, "slug": slug, "status": registry.DEFAULT_STORY_STATUS}
    body = _story_body(title)
    story_md.parent.mkdir(parents=True, exist_ok=True)
    story_md.write_text(f"---\n{dump_frontmatter(fm)}---\n{body}", encoding="utf-8")
    return Result(True, f"created story '{slug}' ({sid}) in epic '{epic_name}'",
                  [epic_md, story_md], entity_id=sid)


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


# ---------------------------------------------------------------------------
# seeds (live in epic.md `## Seeds`)
# ---------------------------------------------------------------------------
def add_seed(graph: Graph, epic_name: str, seed_id: str, status: str = registry.DEFAULT_SEED_STATUS,
             summary: str = "", meta: dict | None = None) -> Result:
    edir = path_mod.epic_dir(graph, epic_name)
    epic_md = edir / "epic.md"
    if not epic_md.exists():
        return Result(False, f"no epic '{epic_name}'")
    if status not in registry.SEED_STATUSES:
        return Result(False, f"invalid status '{status}' (one of {', '.join(registry.SEED_STATUSES)})")
    doc = markdown.split(epic_md.read_text(encoding="utf-8"))
    sec = doc.find_section(registry.SEEDS_HEADING)
    # Update-or-create: `write-epic.md` documents re-running this as updating the seed rather
    # than duplicating it, and the author's bounded rework loops depend on that. The block is
    # fully regenerated from the arguments, so an update is a replace.
    existed = sec is not None and any(c.title.strip() == seed_id for c in sec.children)
    if existed:
        _remove_subsection(doc, registry.SEEDS_HEADING, seed_id)
    block = [f"### {seed_id}", f"- status: {status}"]
    for key in ("surface", "legacySurface", "backing", "prerequisites", "sourceBullet"):
        val = (meta or {}).get(key)
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


def create_spec(graph: Graph, slug: str, doc: str, title: str = "") -> Result:
    """Create — or retro-stamp — a coder process artifact at ``docs/specs/<slug>/<doc>``.

    Idempotent on purpose: the coder writes these docs as free-form markdown, so this has to be
    callable *after* the write as well as before it. An existing file keeps its body and gains only
    the ``type`` it was missing; an already-typed file is left completely alone. No id is allocated
    — a spec is a process artifact, not a graph node (``registry`` requires only ``type``).
    """
    name = doc if doc.endswith(".md") else f"{doc}.md"
    if "/" in slug or "/" in doc:
        return Result(False, f"spec slug/doc must be single path segments, got '{slug}/{doc}'")
    if name in registry.RESERVED_FILES:
        return Result(False, f"'{name}' is a reserved file, not a spec Concept")
    path = graph.doc_roots["specs"] / slug / name
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
