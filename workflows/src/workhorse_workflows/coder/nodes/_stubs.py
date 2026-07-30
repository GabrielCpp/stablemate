"""What the coder's gates return under `--dry-run`.

A dry run replaces every node body with a stand-in, and an undeclared stand-in is a
**blank** instance of the return model. For genesis that reads `ok=False` at every step,
which is not a neutral default: the classifier's `ok=False` is a `raise WorkflowFailed`,
and the validator's `valid=False` is the repair loop, which spends its two reworks on
nothing and then fails the run. A dry run is meant to walk the happy path and prove the
graph is wired; ending it in the error arm proves only that the error arm exists.

So the four gates genesis branches on are declared here. The two that are *not* declared
are as deliberate as the ones that are:

* `select_ci_repo` — blank means `has_repo=False`, which ends the CI loop on its first
  pass. Stubbing it truthy would send a dry run round a poll/fix cycle that has no PR to
  poll and no agent to fix with.
* `gather_run_evidence`, `record_improvements` — dream is linear; nothing branches on
  either, so a blank instance walks the same path a real one does.
"""
from __future__ import annotations

from workhorse_workflows.coder.schemas.genesis import (
    FarrierInstall,
    GenesisReport,
    Skeleton,
    TargetClassification,
)


def classified(*_args: object, **_kwargs: object) -> TargetClassification:
    """`resolve_genesis_target` — a target worth running genesis on.

    `target_state="absent"` on purpose: it is the arm that visits every subsequent state,
    which is what a dry run is for.
    """
    return TargetClassification(ok=True, note="dry run")


def built(*_args: object, **_kwargs: object) -> Skeleton:
    """`init_skeleton` — the stack's init command ran and left its marker."""
    return Skeleton(ok=True, note="dry run")


def installed(*_args: object, **_kwargs: object) -> FarrierInstall:
    """`install_farrier` — adapters rendered and every scaffold took."""
    return FarrierInstall(ok=True, note="dry run")


def valid(*_args: object, **_kwargs: object) -> GenesisReport:
    """`validate_genesis` — the repo satisfies every precondition the main loop assumes."""
    return GenesisReport(valid=True)


__all__ = ["built", "classified", "installed", "valid"]
