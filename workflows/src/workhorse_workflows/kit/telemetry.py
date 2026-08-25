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


def progress_verdict(previous: Sequence[str] | None, current: Sequence[str]) -> str:
    """Classify what one pass of a bounded rework loop did to its outstanding findings.

    A counter says a story was *expensive*; it cannot say whether the expense bought
    anything. Three rework passes each closing real defects and three passes relitigating
    the same brief are the same number, and they want opposite interventions — a larger
    budget in the first case, a prompt repair in the second. This is the distinction.

    ``previous`` is the finding identities the last *failing* pass of this same lane left
    open, and ``None`` when the lane has not failed before; ``current`` is what this pass
    left open. Identities, not counts: a pass that closes two findings and opens two others
    is not the same event as a pass that changed nothing, and only the ids tell them apart.

    One of six words, so the vocabulary stays closed and the label's cardinality bounded:

    ``cleared``     nothing outstanding — the lane converged.
    ``first_pass``  the lane had not failed before; there is no baseline to compare to.
    ``reduced``     fewer outstanding than last pass — the loop is converging.
    ``regressed``   more outstanding than last pass.
    ``stalled``     the same findings, unchanged. The pass bought nothing.
    ``churned``     the same number outstanding, but a different set of them.

    ``churned`` is deliberately not folded into ``stalled``. The repair-pass contract in
    ``coder/docs/prompts/document-story.md`` requires the author to retain stable finding ids, so a
    changed id set is evidence the old worklist *was* closed and new defects were found —
    progress on the items with no net convergence, which is the shape the docs loop
    actually dies of. Note the id stability is a prompt contract rather than an enforced
    one, so ``churned`` is exact on a deterministic lane whose ids are ``path::symbol``
    references and a strong heuristic on a semantic one.

    An empty ``previous`` is read as "this lane has never failed" rather than "it had zero
    findings": a failing gate always names at least one, so the two cannot be confused.
    """
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
