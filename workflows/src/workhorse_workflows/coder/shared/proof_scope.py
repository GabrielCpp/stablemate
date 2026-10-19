"""How much of a story's proof a leftover change reopens: none, the claims that cite it, or all of it."""
from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from pathlib import Path

from workhorse_workflows.coder.shared.schemas.queue import ProofScope


def inert_paths(
    repo_name: str, repo_root: Path, story_path: str, dirty: Iterable[str]
) -> set[str]:
    """The dirty keys of *repo_name* that are the story's own markdown, and nothing else."""
    story = Path(story_path)
    story = story if story.is_absolute() else repo_root / story
    folder = story.parent.resolve()
    prefix = f"{repo_name}:"
    inert: set[str] = set()
    for key in dirty:
        if not key.startswith(prefix):
            continue
        path = (repo_root / key[len(prefix):]).resolve()
        if path.suffix == ".md" and path.parent == folder:
            inert.add(key)
    return inert


def scope(
    changed: Iterable[str],
    inert: Collection[str],
    cited: Mapping[str, Collection[str]],
    covers: Mapping[str, Collection[str]],
    pages: Collection[str] = (),
) -> ProofScope:
    """Decide what a change reruns from the book's citations and the plan's coverage, asking no model."""
    rest = [path for path in changed if path not in inert]
    if not rest:
        return ProofScope(kind="inert")
    claim_pages: set[str] = set()
    reasons: list[str] = []
    for path in rest:
        owned = set(cited.get(path, ()))
        if path in pages:
            owned.add(path)
        if not owned:
            reasons.append(f"{path}: no book page cites it")
            continue
        claim_pages |= owned
        if not any(owned & set(covered) for covered in covers.values()):
            reasons.append(f"{path}: no scenario covers the pages that cite it")
    if reasons:
        return ProofScope(kind="whole", reasons=reasons)
    scenarios = sorted(sid for sid, covered in covers.items() if claim_pages & set(covered))
    return ProofScope(kind="claims", scenarios=scenarios)


__all__ = ["inert_paths", "scope"]
