"""The author's commit: which paths it ships and the message it ships them under."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import registry
from workhorse_workflows.kit import commit_paths, find_repo_root
from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared.schemas.main import Committed


def _commit_message(mode: str, epic: str, bullet: str, roadmap: str = "") -> str:
    if mode == "incomplete":
        if roadmap:
            return f"author: INCOMPLETE — roadmap {Path(roadmap).stem}, do not merge"
        if epic:
            return f"author: INCOMPLETE — unwritten stories, do not merge ({epic})"
        return "author: INCOMPLETE — unwritten stories, do not merge"
    if mode == "story" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        return f"author: {epic} — {trimmed}" if trimmed else f"author: {epic}"
    if mode == "epic-edit" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        epic = registry.epic_slug(epic)
        return f"author: {epic} — {trimmed}" if trimmed else f"author: {epic}"
    if roadmap:
        return f"author: roadmap {Path(roadmap).stem}"
    return "author: epic authoring"


@blueprint.node
def commit_author(
    logger: logging.Logger,
    mode: str = "epic",
    epic: str = "",
    bullet: str = "",
    roadmap: str = "",
    repo_dir: str = "",
    docs_dir: str = "docs",
    id_registry: str = ".agents/ids.json",
) -> Committed:
    """Commit the epic/story docs this run wrote, in the one repo it wrote them in."""
    repo_root = find_repo_root(repo_dir)
    if not (repo_root / ".git").exists():
        logger.info("no .git at %s — nothing to commit", repo_root)
        return Committed()

    scope = [
        rel for rel in (docs_dir.strip(), id_registry.strip()) if rel and (repo_root / rel).exists()
    ]
    if not scope:
        logger.info("nothing author writes exists under %s — nothing to commit", repo_root)
        return Committed()

    committed = commit_paths(repo_root, _commit_message(mode, epic, bullet, roadmap), *scope)
    if committed:
        logger.info("committed %s in %s", " ".join(scope), repo_root)
    return Committed(committed=committed)


__all__ = ["commit_author"]
