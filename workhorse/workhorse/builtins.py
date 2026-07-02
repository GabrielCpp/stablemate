from __future__ import annotations

from typing import Any


def incr(value: Any = 0) -> int:
    try:
        return int(float(value)) + 1
    except (TypeError, ValueError):
        return 1


def seed(**kwargs: Any) -> int:
    return 0


REGISTRY: dict[str, Any] = {
    "incr": incr,
    "seed": seed,
}
