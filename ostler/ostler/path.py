"""``ostler path`` — resolve slugs to canonical filesystem paths.

Uses the graph's configured ``doc_roots`` so custom docRoots from ostler.yml / agents.yml
are respected. All returned paths are relative to the repo root.
"""

from __future__ import annotations

from pathlib import Path

from ostler import registry
from ostler.model import Graph


def resolve_spec(graph: Graph, slug: str) -> str:
    """Resolve a story slug to its spec directory path (relative to root)."""
    specs_root = graph.doc_roots["specs"]
    return str(specs_root.relative_to(graph.root) / slug)


def epic_dirs_in(epics_root: Path) -> list[Path]:
    """Every epic directory under *epics_root*, in name order — creation order, once numbered."""
    if not epics_root.is_dir():
        return []
    return [d for d in sorted(epics_root.iterdir()) if (d / "epic.md").is_file()]


def epic_dirs(graph: Graph) -> list[Path]:
    """Every epic directory on disk, in name order — creation order, once numbered."""
    return epic_dirs_in(graph.doc_roots["epics"])


def epic_dir_in(epics_root: Path, name: str) -> Path:
    """The directory of epic *name* under *epics_root*, by number or by bare slug.

    Epic directories are created numbered (`0001-checkout-flow`, see
    :func:`registry.epic_dir_name`), but the number is presentation, not identity: a bare
    `checkout-flow` still names that epic here, which is what keeps older un-numbered
    epics, hand-written `index.md` lines and slug-only prompts working. A numbered name is
    taken literally — it already says which epic it means, and silently re-pointing
    `0002-x` at `0001-x` would hide a typo. A name that resolves to nothing comes back as
    ``epics_root / name`` so callers keep reporting "no epic '<name>'" against the name
    they were handed.

    Graph-free so that a caller holding only a repo root — a workflow resolving a gate's
    context file, say — resolves an epic folder by the same rule rather than re-deriving a
    second, subtly different one. :func:`epic_dir` is this function against the graph's
    configured epics root.
    """
    name = name.strip()
    if (not name or (epics_root / name / "epic.md").is_file()
            or registry.epic_seq(name) is not None):
        return epics_root / name
    slug = registry.epic_slug(name)
    return next((d for d in epic_dirs_in(epics_root) if registry.epic_slug(d.name) == slug),
                epics_root / name)


def epic_dir(graph: Graph, name: str) -> Path:
    """The directory of epic *name*, whether or not the caller knows its number."""
    return epic_dir_in(graph.doc_roots["epics"], name)


def resolve_epic(graph: Graph, name: str) -> str:
    """Resolve an epic name to its directory path (relative to root)."""
    return str(epic_dir(graph, name).relative_to(graph.root))


def resolve_story(graph: Graph, epic: str, slug: str) -> str:
    """Resolve an epic + story slug to the story.md path (relative to root)."""
    return str(epic_dir(graph, epic).relative_to(graph.root) / "stories" / slug / "story.md")


def resolve_branch(slug: str, *, epic: bool = False) -> str:
    """Resolve a slug to its git branch name.

    An epic branches under ``feat/`` — the one prefix in the system. A story
    branches on its bare id: ids are minted by ostler and carry a repo prefix,
    so they are already globally unique and need no namespace of their own.

    An epic's *sequence number* is dropped: `0003-checkout-flow` branches as
    `feat/checkout-flow`. The number orders the folder listing and says nothing a branch
    name needs, and leaving it in would give the same epic two branch names depending on
    whether the caller had resolved the directory yet.
    """
    if epic:
        return f"feat/{registry.epic_slug(slug)}"
    return slug
