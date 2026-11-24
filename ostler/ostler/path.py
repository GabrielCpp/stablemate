"""``ostler path`` — resolve ids and epic names to canonical filesystem paths."""

from __future__ import annotations

from pathlib import Path

from ostler import model, registry
from ostler.model import Graph


def doc_root_in(root: Path, kind: str) -> Path:
    """The configured directory for doc kind *kind* (``epics``, ``services``, …) under *root*."""
    return model.doc_roots(root, kinds=())[kind]


def epics_root_in(root: Path) -> Path:
    """Where epics live: ``epics/`` at the top level of the artifacts dir."""
    return doc_root_in(root, "epics")


def epics_root(graph: Graph) -> Path:
    """Where epics live in this graph."""
    return graph.doc_roots["epics"]


def specs_root_in(root: Path) -> Path:
    """Where story specs live under *root*."""
    return doc_root_in(root, "specs")


def register_root_in(root: Path) -> Path:
    """Where the Register's records live for *root*: ``backlogs/`` in the artifacts dir, never in a code repo."""
    return doc_root_in(root, "register")


def register_root(graph: Graph) -> Path:
    """Where the Register's records live for this graph."""
    return graph.doc_roots["register"]


def decisions_root_in(root: Path) -> Path:
    """Where the decisions live for *root*: ``docs/decisions`` in the artifacts dir."""
    return doc_root_in(root, "decisions")


def adr_root_in(root: Path) -> Path:
    """Where the decision records live for *root*: ``docs/adrs`` in the artifacts dir."""
    return doc_root_in(root, "adrs")


def adr_root(graph: Graph) -> Path:
    """Where the decision records live for this graph."""
    return graph.doc_roots["adrs"]


def resolve_spec_arg(root: Path, spec: Path) -> Path:
    """A ``--spec`` value as an absolute path: as typed, else under the specs root, else under *root*."""
    if spec.is_absolute():
        return spec
    under_specs = specs_root_in(root) / spec
    under_root = root / spec
    if under_specs.exists() or not under_root.exists():
        return under_specs
    return under_root


def display_path(root: Path, path: Path) -> str:
    """*path* relative to *root* when it sits inside it, absolute otherwise."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_spec(graph: Graph, story: str) -> str:
    """Resolve a story id to its spec directory path (absolute); an unknown id is an error, never a folder."""
    found = graph.find_story(story)
    if found is None:
        raise ValueError(graph.no_story(story))
    return str(graph.doc_roots["specs"] / found[1].eid)


def epic_dirs_under(epics_root: Path) -> list[Path]:
    """Every epic directory directly under *epics_root*, in name order."""
    if not epics_root.is_dir():
        return []
    return [d for d in sorted(epics_root.iterdir()) if (d / "epic.md").is_file()]


def epic_dirs_in(root: Path) -> list[Path]:
    """Every epic directory under *root*, in name order — creation order, once numbered."""
    return epic_dirs_under(epics_root_in(root))


def epic_dirs(graph: Graph) -> list[Path]:
    """Every epic directory on disk, in name order — creation order, once numbered."""
    return epic_dirs_under(epics_root(graph))


def _epic_names(epic_md: Path) -> tuple[str, str]:
    """The id and the slug an epic.md declares, the slug read off an old ``NNNN-slug`` folder when it declares none."""
    fm = model.read_doc(epic_md).frontmatter or {}
    slug = str(fm.get("slug") or "").strip() or registry.epic_slug(epic_md.parent.name)
    return str(fm.get("id") or "").strip(), slug


def epic_dir_under(epics_root: Path, name: str) -> Path:
    """:func:`epic_dir_in`'s resolution against an epics directory the caller names: the folder, the id, then the slug."""
    name = name.strip()
    if not name or (epics_root / name / "epic.md").is_file():
        return epics_root / name
    slug = registry.epic_slug(name)
    named = [(d, *_epic_names(d / "epic.md")) for d in epic_dirs_under(epics_root)]
    return next((d for d, eid, _ in named if eid == name),
                next((d for d, _, s in named if s == slug), epics_root / name))


def epic_slug_in(root: Path, name: str) -> str:
    """The slug epic *name* (its folder, id or slug) declares under *root*, else *name* read as an old ``NNNN-slug``."""
    epic_md = epic_dir_in(root, name) / "epic.md"
    return _epic_names(epic_md)[1] if epic_md.is_file() else registry.epic_slug(name)


def epic_dir_in(root: Path, name: str) -> Path:
    """The directory of epic *name* under *root*, by folder, id or slug."""
    return epic_dir_under(epics_root_in(root), name)


def epic_dir(graph: Graph, name: str) -> Path:
    """The directory of epic *name*, by folder, id or slug."""
    return epic_dir_under(epics_root(graph), name)


def _story_id_under(epic_dir_path: Path, story: str) -> str:
    """The id the epic's `## Stories` block gives the story filed under slug *story*, else *story* itself."""
    epic_md = epic_dir_path / "epic.md"
    if not epic_md.is_file():
        return story
    section = model.read_doc(epic_md).find_section(registry.STORIES_HEADING)
    for sub in section.children if section is not None else []:
        if sub.title.strip() == story:
            return model._meta_scalar(model._meta_from_bullets(sub), "id") or story
    return story


def story_dir_in(root: Path, epic: str, story: str) -> Path:
    """The folder of *story* (its id or its slug) in *epic*: ``<epic-dir>/stories/<story-id>``."""
    return story_dir_under(epic_dir_in(root, epic), story)


def story_dir(graph: Graph, epic: str, story: str) -> Path:
    """The folder of *story* (its id or its slug) in *epic* for this graph."""
    return story_dir_under(epic_dir(graph, epic), story)


def story_dir_under(epic_dir_path: Path, story: str) -> Path:
    """The folder of *story* (its id or its slug) under an epic directory the caller already holds."""
    return epic_dir_path / "stories" / _story_id_under(epic_dir_path, story)


def resolve_epic(graph: Graph, name: str) -> str:
    """Resolve an epic name to its directory path (relative to root)."""
    return display_path(graph.root, epic_dir(graph, name))


def resolve_story(graph: Graph, story: str) -> str:
    """Resolve a story id to its story.md path (relative to root)."""
    found = graph.find_story(story)
    if found is None:
        raise ValueError(graph.no_story(story))
    epic, s = found
    return display_path(graph.root, s.story_md or epic.directory / "stories" / s.eid / "story.md")


def resolve_branch(graph: Graph, ref: str, *, epic: bool = False) -> str:
    """The git branch for a story id (its slug) or, with *epic*, for an epic name (``feat/<slug>``)."""
    if epic:
        found_epic = graph.epic_by_ref(ref)
        return f"feat/{found_epic.slug if found_epic is not None else registry.epic_slug(ref)}"
    found = graph.find_story(ref)
    if found is None:
        raise ValueError(graph.no_story(ref))
    return found[1].slug
