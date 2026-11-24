"""The author's commit: which paths it ships and the message it ships them under."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse_workflows.kit import commit_paths, find_docs_root
from workhorse_workflows.kit.paths import artifacts_root, milestone_key
from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared.schemas.main import Committed


def _commit_message(mode: str, epic: str, bullet: str, milestone: str = "") -> str:
    if mode == "incomplete":
        if milestone:
            return f"author: INCOMPLETE — milestone {Path(milestone).parent.name}, do not merge"
        if epic:
            return f"author: INCOMPLETE — unwritten stories, do not merge ({epic})"
        return "author: INCOMPLETE — unwritten stories, do not merge"
    if mode == "story" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        return f"author: {epic} — {trimmed}" if trimmed else f"author: {epic}"
    if mode == "epic-edit" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        return f"author: {epic} — {trimmed}" if trimmed else f"author: {epic}"
    if milestone:
        return f"author: milestone {Path(milestone).parent.name}"
    return "author: epic authoring"


@blueprint.node
def commit_author(
    logger: logging.Logger,
    mode: str = "epic",
    epic: str = "",
    bullet: str = "",
    milestone: str = "",
    repo_dir: str = "",
    docs_dir: str = "docs",
) -> Committed:
    """Commit the epic/story docs this run wrote, in the one repo it wrote them in."""
    message = _commit_message(mode, epic, bullet, milestone)
    committed = _commit_docs(logger, find_docs_root(repo_dir), docs_dir.strip(), message)
    if milestone:
        committed = _commit_milestone(logger, milestone, message) or committed
    return Committed(committed=committed)


def _commit_docs(logger: logging.Logger, repo_root: Path, docs: str, message: str) -> bool:
    if not (repo_root / ".git").exists():
        logger.info("no .git at %s — nothing to commit", repo_root)
        return False
    if not docs or not (repo_root / docs).exists():
        logger.info("nothing author writes exists under %s — nothing to commit", repo_root)
        return False
    committed = commit_paths(repo_root, message, docs)
    if committed:
        logger.info("committed %s in %s", docs, repo_root)
    return committed


def _commit_milestone(logger: logging.Logger, milestone: str, message: str) -> bool:
    artifacts = artifacts_root()
    if not (artifacts / ".git").exists():
        return False
    key = milestone_key(artifacts / milestone)
    folder = Path(key).parent.as_posix()
    committed = commit_paths(artifacts, message, folder)
    if committed:
        logger.info("committed %s in %s", folder, artifacts)
    return committed


__all__ = ["commit_author"]
