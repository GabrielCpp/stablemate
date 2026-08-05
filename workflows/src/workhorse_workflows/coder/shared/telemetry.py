"""Bounded retry budgets, reported as span dimensions.

Every machine here is a loop with a ceiling on it, and until these labels existed the
ceiling was the only part visible from outside. A span from the third repair pass looked
exactly like a span from the first, so the question the budgets are *for* — is this gate
catching real defects, or cycling — could not be asked of the telemetry at all. It could
only be reconstructed afterwards from a give-up note, and only for work that gave up. Work
that passed on its fourth attempt left no trace that there had been four.

The counters need no new bookkeeping to reach a span: each is already a state parameter,
because state parameters are the checkpoint, and `Workflow.state_labels` is handed exactly
those. So this module is only the shaping — reading the named counters out of a params
dict and stringifying them under a per-flow prefix.

Two rules are deliberate. A counter the current state does not take is **absent** rather
than `0`: a state without the parameter has no opinion about that budget, and stamping a
zero would read as "first attempt" on every span of every state that never sees it, which
is worse than silence. And only ints are reported, which bounds cardinality to the budget
ceilings (2 or 3) — a label is stamped on every span opened while it is current, so a
free-text value here would multiply the store, not describe it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def counter_labels(
    source: Mapping[str, Any], prefix: str, names: Sequence[str]
) -> dict[str, str]:
    """The named integer counters in `source`, as `{prefix}.{name}` labels.

    `source` is a state's bound parameters, or the dump of a loop object carrying them.
    Anything absent, non-integer, or boolean is skipped — `bool` explicitly, since it is
    an `int` subclass in Python and a flag is not an attempt count.
    """
    labels = {}
    for name in names:
        value = source.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            labels[f"{prefix}.{name}"] = str(value)
    return labels


def verdict_labels(
    source: Mapping[str, Any], prefix: str, names: Sequence[str]
) -> dict[str, str]:
    """The named non-empty string verdicts in `source`, as `{prefix}.{name}` labels.

    A gate's disposition is what makes the counters legible: "four plan-QA attempts" is a
    cost, "four attempts, each ending `revise`" is a diagnosis. Blank is skipped, since a
    gate that has not run yet has said nothing — distinct from one that said nothing was
    wrong.

    Cardinality is bounded by the gates' own vocabularies, which are closed sets of a
    handful of words each (`approved`/`revise`, `stands`/`refuted`, and so on).
    """
    labels = {}
    for name in names:
        value = source.get(name)
        if isinstance(value, str) and value:
            labels[f"{prefix}.{name}"] = value
    return labels
