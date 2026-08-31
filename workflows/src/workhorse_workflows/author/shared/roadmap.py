"""The repo's one approved roadmap — discovered, never named by a parameter."""
from __future__ import annotations

from pathlib import Path

from ostler import markdown
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared import paths


def approved_roadmap(root: Path) -> str:
    """The one roadmap this repo authors from, repo-relative, or stop before a turn.

    Discovered rather than named. A `roadmap` parameter would be a second record of a
    location `docRoots:` already gives, and a run pointed at a file outside the roadmaps
    root authors epics against a plan ostler cannot see. Which roadmap is *approved* is a
    fact the documents carry in their own frontmatter, so it is read from them.

    Two approved roadmaps is an ambiguity the tree has to settle, not one this function may
    pick a winner for; both are named so the operator can retire one.
    """
    roadmaps = paths.roadmaps_dir(root)
    directory = root / roadmaps
    candidates = sorted(directory.glob("*.md")) if directory.is_dir() else []
    approved = [
        candidate.relative_to(root).as_posix()
        for candidate in candidates
        if _is_approved(candidate)
    ]
    if not approved:
        raise WorkflowFailed(
            f"authoring requires one roadmap with `type: roadmap` and `status: approved` "
            f"under {roadmaps}/; none of the {len(candidates)} file(s) there qualifies. "
            f"Point `docRoots: roadmaps:` at the directory this repo keeps them in if it "
            f"is not that one."
        )
    if len(approved) > 1:
        raise WorkflowFailed(
            f"authoring requires exactly one approved roadmap; {roadmaps}/ has "
            f"{len(approved)}: {', '.join(approved)}. Retire the ones this run should not "
            f"author from."
        )
    return approved[0]


def _is_approved(candidate: Path) -> bool:
    """Does this file say, in its own frontmatter, that it is the approved roadmap?"""
    frontmatter = markdown.split(candidate.read_text(encoding="utf-8")).frontmatter or {}
    return frontmatter.get("type") == "roadmap" and frontmatter.get("status") == "approved"


__all__ = ["approved_roadmap"]
