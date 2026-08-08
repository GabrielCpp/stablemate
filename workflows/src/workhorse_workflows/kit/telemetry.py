"""Bounded retry budgets and gate verdicts, reported as span dimensions.

The counters need no new bookkeeping to reach a span: each is already a state parameter,
because state parameters are the checkpoint, and ``Workflow.state_labels`` is handed exactly
those. This module only shapes named values under a per-flow prefix.

A counter the current state does not take is absent rather than ``0``, and only integers are
reported. Verdicts are restricted by their callers to closed, low-cardinality vocabularies.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


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
