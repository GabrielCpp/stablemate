"""The hashes that bind a run's decisions to the bytes they were made about."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ostler import markdown


def milestone_body_digest(root: Path, milestone_path: str) -> str:
    """The sha256 of the milestone body, which no run writes."""
    text = (root / milestone_path).read_text(encoding="utf-8")
    return hashlib.sha256(markdown.split(text).body.encode("utf-8")).hexdigest()


__all__ = ["milestone_body_digest"]
