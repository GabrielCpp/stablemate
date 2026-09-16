"""The declared dry-run stand-ins.

`--dry-run` drives the machine with every node replaced by a stand-in, and an undeclared
one is `returns.model_construct()` — every bool `False`. That default is the *pessimistic*
answer at each of this workflow's gates, and the pessimistic answer here is not "take the
other arm" but "loop": a blank checkpoint is never clean, a blank coverage never complete,
so the drain would circle until the transition budget ran out and report a stalled machine
rather than a walked graph.

Each stand-in below is therefore the affirmative answer at one gate — the reading that
makes the run *progress*. The untaken arms are not skipped by this: the static preflight
checks every branch and every prompt path whether or not the stubbed drive reaches it.

`select_item`'s blank is left alone deliberately. `has_item=False, over_budget=False` is
what converges both drain loops in one hop, and it is exactly what an empty worklist
returns for real.
"""
from __future__ import annotations

from workhorse_workflows.okf_builder.shared.schemas import Checkpoint, Coverage, Prepared


def prepared(*_args: object, **_kwargs: object) -> Prepared:
    """A repo whose graph ostler can read — the only setting that gets past `start`."""
    return Prepared(ostler_ok=True)


def clean(*_args: object, **_kwargs: object) -> Checkpoint:
    """A book `ostler doctor` has nothing to say about."""
    return Checkpoint(checkpoint_clean=True)


def covered(*_args: object, **_kwargs: object) -> Coverage:
    """An inventory the book already cites in full."""
    return Coverage(coverage_complete=True)


__all__ = ["clean", "covered", "prepared"]
