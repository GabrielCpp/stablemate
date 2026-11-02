from __future__ import annotations

import os
from typing import Any

Signature = tuple[tuple[str, str], ...]

_RESERVED_ATTRS = ("workhorse.", "status_message", "events")


def repeats() -> int:
    return int(os.environ.get("GROOM_CHURN_REPEATS", "5"))


def label_signature(attrs: dict[str, Any]) -> Signature:
    """The workflow-declared dimensions on a span, as a comparable key."""
    return tuple(
        sorted(
            (key, str(value))
            for key, value in attrs.items()
            if not key.startswith(_RESERVED_ATTRS[0]) and key not in _RESERVED_ATTRS[1:]
        )
    )


def counts_as_visit(span: dict[str, Any]) -> bool:
    """A node span that ended on its own, not one a live reload cut short."""
    node = span.get("node") or ""
    return bool(node) and span.get("name") == node and not (span.get("attrs") or {}).get("workhorse.cut")


def observe(labels: dict[str, Signature], counts: dict[str, int], node: str, attrs: dict[str, Any]) -> tuple[int, bool]:
    """Fold one finished visit into the per-node tally. Returns the repeat count and whether the work moved on."""
    signature = label_signature(attrs)
    if labels.get(node) != signature:
        labels[node] = signature
        counts[node] = 1
        return 1, True
    counts[node] = counts.get(node, 0) + 1
    return counts[node], False


def alerts(spans: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    """The churn alerts the stored spans would have fired, each as the visit that tipped it and its repeat count, replaying them in the order they ended."""
    labels: dict[str, Signature] = {}
    counts: dict[str, int] = {}
    fired = False
    generation = None
    found: list[tuple[dict[str, Any], int]] = []
    limit = repeats()
    for span in sorted(spans, key=lambda item: (item["end_ts"], item["start_ts"])):
        if span.get("resume_generation") != generation and span.get("resume_generation") is not None:
            if generation is not None:
                fired = False
            generation = span["resume_generation"]
        if not counts_as_visit(span):
            continue
        count, moved = observe(labels, counts, span["node"], span["attrs"])
        if moved:
            fired = False
        if count >= limit and not fired:
            fired = True
            found.append((span, count))
    return found


def count_alerts(spans: list[dict[str, Any]]) -> int:
    """How many churn alerts the stored spans would have fired."""
    return len(alerts(spans))
