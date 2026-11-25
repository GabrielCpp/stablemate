"""Value coercers shared by the machine config tables."""

from __future__ import annotations

import math
from typing import Any, Literal

BUILTIN_DEFAULT_CLI = "claude"


def text_or_none(raw: Any) -> str | None:
    """A non-empty string, or ``None`` for anything else: a malformed path reads as unset."""
    return raw if isinstance(raw, str) and raw else None


def cli_name(raw: Any) -> str:
    """A CLI name trimmed and lowercased; anything unusable reads as the built-in default."""
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return BUILTIN_DEFAULT_CLI


def positive_finite(raw: Any) -> float | None:
    """A strictly positive, finite number as a float, or ``None`` for anything else."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        return None
    return value


MIN_COMPACT_WINDOW = 100000


def compact_window_or_none(raw: Any) -> int | Literal["auto"] | None:
    """A token count of at least 100000, or ``"auto"``; anything else reads as unset."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= MIN_COMPACT_WINDOW else None
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        return "auto"
    return None
