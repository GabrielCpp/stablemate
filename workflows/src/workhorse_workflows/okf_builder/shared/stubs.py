"""The declared dry-run stand-ins."""
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
