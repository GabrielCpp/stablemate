"""The unit statuses a survey inventory holds, and the file name of each unit's finding record."""
from __future__ import annotations

import re

UNIT_STATUSES = {"pending", "assessed", "clean", "blocked"}


def record_slug(unit_id: str) -> str:
    """Filename-safe slug a unit's finding record is stored under (findings/<slug>.md)."""
    return re.sub(r"[^a-z0-9]+", "-", unit_id.lower()).strip("-")


__all__ = ["UNIT_STATUSES", "record_slug"]
