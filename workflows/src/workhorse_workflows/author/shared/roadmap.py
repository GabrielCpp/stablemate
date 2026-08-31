"""Approved-roadmap intake shared by the milestone and epic-split machines."""
from __future__ import annotations

from pathlib import Path

from ostler import markdown
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared import paths


def approved_roadmap(root: Path, roadmap: str) -> str:
    """Return a normalized approved roadmap path or stop before an authoring turn."""
    resolved = paths.roadmap_file(root, roadmap)
    if not resolved:
        raise WorkflowFailed("an approved roadmap file is required")
    target = (root / resolved).resolve()
    try:
        relative = target.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkflowFailed(f"roadmap must be inside the repository: {target}") from exc
    if relative.parent != Path("docs/roadmaps") or relative.suffix != ".md" or not target.is_file():
        raise WorkflowFailed(f"roadmap must be one markdown file under docs/roadmaps/: {resolved}")
    frontmatter = markdown.split(target.read_text(encoding="utf-8")).frontmatter or {}
    if frontmatter.get("type") != "roadmap" or frontmatter.get("status") != "approved":
        raise WorkflowFailed(f"authoring requires an approved roadmap at {resolved}")
    return resolved


__all__ = ["approved_roadmap"]
