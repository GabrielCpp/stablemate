"""Durable proof that the PM passed the exact bytes a stage produced."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ostler import Ostler
from ostler.model import Epic
from workhorse_workflows.author.shared.digests import milestone_body_digest

RECEIPT_NAME = "pm-receipt.json"
MILESTONE_ARTIFACTS = "artifacts"


def story_digest(story_md: Path) -> str:
    """The sha256 of the story's bytes, so any edit to it voids the pass."""
    return hashlib.sha256(story_md.read_bytes()).hexdigest()


def story_split_digest(epic: Epic) -> str:
    """Hash only split-owned scope, so later story prose edits keep the pass valid."""
    payload = {
        "seeds": [seed.id for seed in epic.seeds if seed.active],
        "stories": [
            {
                "slug": story.slug,
                "title": story.title,
                "covers": story.seed_items,
                "dependsOn": story.dependencies,
            }
            for story in epic.stories
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def epic_split_digest(root: Path, milestone_path: str, epics: list[str]) -> str:
    """Hash the milestone's ordered epic list together with its body digest."""
    payload = {
        "epics": [str(epic).strip() for epic in epics],
        "body": milestone_body_digest(root, milestone_path),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def receipt_target(root: Path, stage: str, subject: str) -> tuple[Path, str] | None:
    """The directory a stage's receipt lives in and the digest it binds, or nothing for a stage with no durable subject."""
    if stage == "story":
        story_md = root / subject
        return story_md.parent, story_digest(story_md)
    graph = Ostler(root).graph
    if stage == "story-split":
        folder = (root / subject).resolve()
        for epic in graph.epics:
            if epic.epic_md is not None and epic.epic_md.parent.resolve() == folder:
                return epic.epic_md.parent, story_split_digest(epic)
        return None
    if stage == "epic-split":
        milestone_md = (root / subject).resolve()
        for milestone in graph.milestones:
            if milestone.path.resolve() == milestone_md:
                digest = epic_split_digest(root, subject, milestone.epics)
                return milestone.path.parent / MILESTONE_ARTIFACTS, digest
    return None


def write_pm_receipt(directory: Path, stage: str, digest: str) -> Path:
    """Write the pass for *stage* into *directory* and return the file."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / RECEIPT_NAME
    path.write_text(
        json.dumps({"stage": stage, "status": "passed", "digest": digest}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def pm_receipt_current(directory: Path, stage: str, digest: str) -> bool:
    """Whether *directory* holds a pass of *stage* bound to exactly *digest*."""
    try:
        data = json.loads((directory / RECEIPT_NAME).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    return (
        isinstance(data, dict)
        and data.get("stage") == stage
        and data.get("status") == "passed"
        and data.get("digest") == digest
    )


__all__ = [
    "MILESTONE_ARTIFACTS",
    "RECEIPT_NAME",
    "epic_split_digest",
    "pm_receipt_current",
    "receipt_target",
    "story_digest",
    "story_split_digest",
    "write_pm_receipt",
]
