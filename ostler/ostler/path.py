"""``ostler path`` — resolve slugs to canonical filesystem paths."""

from __future__ import annotations

from pathlib import Path

from ostler import model, registry
from ostler.model import Graph


def doc_root_in(root: Path, kind: str) -> Path:
    """The configured directory for doc kind *kind* (``epics``, ``services``, …) under *root*."""
    return model.doc_roots(root, kinds=())[kind]


def epics_root_in(root: Path) -> Path:
    """Where epics live under *root* — ``docs/epics``."""
    return doc_root_in(root, "epics")


def epics_root(graph: Graph) -> Path:
    """Where epics live in this graph."""
    return graph.doc_roots["epics"]


def services_root_in(root: Path, service: str = "") -> Path:
    """The feature book under *root*, scoped to one *service* when the repo has several."""
    base = doc_root_in(root, "services")
    return base / service if service else base


def services_root(graph: Graph, service: str = "") -> Path:
    """The feature book in this graph, scoped to one *service* when there is one."""
    base = graph.doc_roots.get("services") or (graph.root / "docs" / "services")
    return base / service if service else base


def resolve_services_root(value: str | None, root: Path) -> str:
    """The `servicesRoot` a QA context packet names, normalised against *root*."""
    stripped = (value or "").strip()
    return stripped or services_root_in(root).relative_to(root).as_posix()


def book_prefix_in(root: Path, services_root: str) -> str:
    """Where a book is nested under *root*, relative to it — `""` when it is not nested."""
    default_suffix = services_root_in(root).relative_to(root).as_posix()
    if not services_root or services_root == default_suffix:
        return ""
    suffix = f"/{default_suffix}"
    return services_root[: -len(suffix)] if services_root.endswith(suffix) else ""


def book_root_in(root: Path, services_root: str) -> Path:
    """The root of the system the book at *services_root* describes."""
    prefix = book_prefix_in(root, services_root)
    return root / prefix if prefix else root


def specs_root_in(root: Path) -> Path:
    """Where story specs live under *root*."""
    return doc_root_in(root, "specs")


def backlog_path_in(root: Path) -> Path:
    """The intake list, ``docs/backlog.md`` under *root*."""
    return doc_root_in(root, "backlog")


def backlog_path(graph: Graph) -> Path:
    """The intake list for this graph."""
    return graph.doc_roots["backlog"]


def register_root_in(root: Path) -> Path:
    """Where the Register's records live for *root*: ``backlog/`` in the artifacts dir, never in a code repo."""
    return doc_root_in(root, "register")


def register_root(graph: Graph) -> Path:
    """Where the Register's records live for this graph."""
    return graph.doc_roots["register"]


def adr_root_in(root: Path) -> Path:
    """Where the decision records live for *root*: ``adr/`` in the artifacts dir, beside the Register's shelf."""
    return doc_root_in(root, "adr")


def adr_root(graph: Graph) -> Path:
    """Where the decision records live for this graph."""
    return graph.doc_roots.get("adr") or register_root(graph).parent / "adr"


def epics_index_in(root: Path) -> Path:
    """The epic queue, ``index.md`` in the epics root — its front entry is the current epic."""
    return epics_root_in(root) / "index.md"


def epics_index(graph: Graph) -> Path:
    """The epic queue for this graph."""
    return epics_root(graph) / "index.md"


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
    """Resolve a story to its spec directory path (absolute), named by the story's id."""
    found = graph.find_story(story)
    if found is None:
        return str(graph.doc_roots["specs"] / story)
    _, s = found
    if not s.eid:
        raise ValueError(
            f"story '{s.slug}' has no id, so it has no spec folder: give it an `id:` first "
            f"(`ostler create story` mints one)")
    return str(graph.doc_roots["specs"] / s.eid)


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


def epic_dir_under(epics_root: Path, name: str) -> Path:
    """:func:`epic_dir_in`'s resolution against an epics directory the caller names."""
    name = name.strip()
    if (not name or (epics_root / name / "epic.md").is_file()
            or registry.epic_seq(name) is not None):
        return epics_root / name
    slug = registry.epic_slug(name)
    return next((d for d in epic_dirs_under(epics_root) if registry.epic_slug(d.name) == slug),
                epics_root / name)


def epic_dir_in(root: Path, name: str) -> Path:
    """The directory of epic *name* under *root*, by number or by bare slug."""
    return epic_dir_under(epics_root_in(root), name)


def epic_dir(graph: Graph, name: str) -> Path:
    """The directory of epic *name*, whether or not the caller knows its number."""
    return epic_dir_under(epics_root(graph), name)


def story_dir_in(root: Path, epic: str, slug: str) -> Path:
    """The folder of story *slug* in *epic*: ``<epic-dir>/stories/<slug>``."""
    return epic_dir_in(root, epic) / "stories" / slug


def story_dir(graph: Graph, epic: str, slug: str) -> Path:
    """The folder of story *slug* in *epic* for this graph."""
    return epic_dir(graph, epic) / "stories" / slug


def story_dir_under(epic_dir_path: Path, slug: str) -> Path:
    """The folder of story *slug* under an epic directory the caller already holds."""
    return epic_dir_path / "stories" / slug


def waivers_path_under(services_root_path: Path) -> Path:
    """A book's coverage waivers, for a caller that already holds the book directory."""
    return services_root_path / "coverage-waivers.json"


def waivers_path_in(root: Path, service: str = "") -> Path:
    """A feature book's coverage waivers, ``coverage-waivers.json`` beside the book itself."""
    return waivers_path_under(services_root_in(root, service))


def waivers_path(graph: Graph, service: str = "") -> Path:
    """This graph's coverage waivers, for one *service*'s book when there is one."""
    return waivers_path_under(services_root(graph, service))


def screenshots_dir_under(services_root_path: Path) -> Path:
    """A book's registered screenshots, for a caller that already holds the book directory."""
    return services_root_path / "gui" / "screenshots"


def screenshots_dir_in(root: Path, service: str = "") -> Path:
    """Where a walkthrough's registered screenshots live: ``<book>/gui/screenshots``."""
    return screenshots_dir_under(services_root_in(root, service))


def screenshots_dir(graph: Graph, service: str = "") -> Path:
    """This graph's registered screenshots, for one *service*'s book when there is one."""
    return screenshots_dir_under(services_root(graph, service))


def resolve_epic(graph: Graph, name: str) -> str:
    """Resolve an epic name to its directory path (relative to root)."""
    return str(epic_dir(graph, name).relative_to(graph.root))


def resolve_story(graph: Graph, epic: str, slug: str) -> str:
    """Resolve an epic + story slug to the story.md path (relative to root)."""
    return str(epic_dir(graph, epic).relative_to(graph.root) / "stories" / slug / "story.md")


def resolve_branch(slug: str, *, epic: bool = False) -> str:
    """Resolve a slug to its git branch name."""
    if epic:
        return f"feat/{registry.epic_slug(slug)}"
    return slug
