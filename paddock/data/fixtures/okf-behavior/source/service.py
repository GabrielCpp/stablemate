"""A bounded dispatch operation with observable errors, defaults and effects."""
from __future__ import annotations


def dispatch(items: list[str], sent: list[str], limit: int = 2) -> dict[str, object]:
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    if not items:
        return {"status": "empty", "count": 0}
    selected = items[:limit]
    sent.extend(selected)
    return {"status": "sent", "count": len(selected)}
