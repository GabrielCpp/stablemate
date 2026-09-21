"""Bounded retry budgets and gate verdicts, reported as span dimensions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

ProgressVerdict = Literal[
    "cleared", "first_pass", "reduced", "regressed", "stalled", "churned"
]


def counter_labels(
    source: Mapping[str, Any], prefix: str, names: Sequence[str]
) -> dict[str, str]:
    """Return named integer counters as ``{prefix}.{name}`` labels."""
    labels = {}
    for name in names:
        value = source.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            labels[f"{prefix}.{name}"] = str(value)
    return labels


def verdict_labels(
    source: Mapping[str, Any], prefix: str, names: Sequence[str]
) -> dict[str, str]:
    """Return named non-empty string verdicts as ``{prefix}.{name}`` labels."""
    labels = {}
    for name in names:
        value = source.get(name)
        if isinstance(value, str) and value:
            labels[f"{prefix}.{name}"] = value
    return labels


def progress_verdict(
    previous: Sequence[str] | None, current: Sequence[str]
) -> ProgressVerdict:
    """Classify what one pass of a bounded rework loop did to its outstanding findings."""
    before = set(previous) if previous else set()
    now = set(current)
    if not now:
        return "cleared"
    if not before:
        return "first_pass"
    if len(now) < len(before):
        return "reduced"
    if len(now) > len(before):
        return "regressed"
    return "stalled" if now == before else "churned"
