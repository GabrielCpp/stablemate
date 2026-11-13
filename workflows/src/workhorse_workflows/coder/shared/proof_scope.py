"""How much of a story's proof a leftover change reopens: none, or all of it."""
from __future__ import annotations

from collections.abc import Collection, Iterable
from pathlib import Path

from workhorse_workflows.coder.shared.schemas.queue import ProofScope
from workhorse_workflows.coder.shared.worktree import is_product


def inert_paths(
    repo_name: str,
    repo_root: Path,
    story_path: str,
    dirty: Iterable[str],
    excluded: Collection[Path] = (),
) -> set[str]:
    """The dirty keys of *repo_name* no proof depends on: the story's own markdown, and any path that is not product under *excluded*."""
    story = Path(story_path)
    story = story if story.is_absolute() else repo_root / story
    folder = story.parent.resolve()
    prefix = f"{repo_name}:"
    inert: set[str] = set()
    for key in dirty:
        if not key.startswith(prefix):
            continue
        rel = key[len(prefix):]
        path = (repo_root / rel).resolve()
        if (path.suffix == ".md" and path.parent == folder) or (
            excluded and not is_product(repo_root, rel, list(excluded))
        ):
            inert.add(key)
    return inert


def scope(changed: Iterable[str], inert: Collection[str]) -> ProofScope:
    """Decide what a change reruns: nothing when every path is inert, else the whole proof."""
    rest = [path for path in changed if path not in inert]
    if not rest:
        return ProofScope(kind="inert")
    return ProofScope(
        kind="whole",
        reasons=[f"{path}: changed after the passing QA saw it" for path in rest],
    )


__all__ = ["inert_paths", "scope"]
