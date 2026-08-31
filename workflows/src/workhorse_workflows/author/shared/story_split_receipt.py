"""Durable evidence that one epic's story topology passed semantic review."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ostler.model import Epic

RECEIPT_NAME = "story-split-receipt.json"


def story_split_digest(epic: Epic) -> str:
    """Hash only split-owned scope, so later story prose edits keep the review valid."""
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


def story_split_receipt_path(epic: Epic) -> Path | None:
    """Return the receipt beside epic.md when the epic has a persisted document."""
    return epic.epic_md.parent / RECEIPT_NAME if epic.epic_md is not None else None


def story_split_review_current(epic: Epic) -> bool:
    """Whether the persisted semantic review covers the exact current topology."""
    receipt = story_split_receipt_path(epic)
    if receipt is None:
        return False
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False
    return (
        data.get("status") == "passed"
        and data.get("graphDigest") == story_split_digest(epic)
    )


__all__ = [
    "RECEIPT_NAME",
    "story_split_digest",
    "story_split_receipt_path",
    "story_split_review_current",
]
