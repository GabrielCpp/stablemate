"""``ostler path`` — resolve slugs to canonical filesystem paths.

Uses the graph's configured ``doc_roots`` so custom docRoots from ostler.yml / agents.yml
are respected. All returned paths are relative to the repo root.
"""

from __future__ import annotations

from .model import Graph


def resolve_spec(graph: Graph, slug: str) -> str:
    """Resolve a story slug to its spec directory path (relative to root)."""
    specs_root = graph.doc_roots["specs"]
    return str(specs_root.relative_to(graph.root) / slug)


def resolve_story(graph: Graph, epic: str, slug: str) -> str:
    """Resolve an epic + story slug to the story.md path (relative to root)."""
    epics_root = graph.doc_roots["epics"]
    return str(epics_root.relative_to(graph.root) / epic / "stories" / slug / "story.md")


def resolve_branch(slug: str, *, epic: bool = False) -> str:
    """Resolve a slug to its git branch name."""
    if epic:
        return f"feat/{slug}"
    return f"story/{slug}"
