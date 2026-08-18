"""The dream flow's models: what a finished run did, and what should change because of it.

Ported from the `dream` flow's two script nodes and its one agent turn. `dream` reads a
*previous* run's telemetry — not its own — and turns whatever the run struggled with into
entries in a durable improvement ledger.

`digest` is the one loosely-typed value in the port. It is a summary the reflection prompt
reads as JSON, its keys are chosen by `gather_run_evidence` and never branched on, and
pinning it into a model would mean re-declaring nine derived statistics for the sake of a
schema nothing validates against. It is `dict[str, Any]`, and the keys are documented on
the node that builds it.
"""
from __future__ import annotations

from typing import Any

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class RunEvidence(CoderResult):
    """`gather-run-evidence.py` — the digest, and the run directory it came from.

    `run_dir` is echoed back because the node **resolves** it: given nothing, it picks the
    most recently active non-dream run under the docs root, and every node after it needs
    the directory that was actually read rather than the argument that was passed.
    """

    run_dir: str = ""
    digest: dict[str, Any] = {}


class ReflectionResult(CoderResult):
    """`prompts/dream-reflect.md` — what the reflection turn concluded.

    `status` is `reflected`, `no_issues`, `insufficient_evidence` or `blocked`, and
    `top_layer` names the layer most of the proposals landed in. Neither is branched on;
    the proposals themselves go to disk, in the inbox `record_improvements` drains.
    `insufficient_evidence` is a thin run, which is ordinary; `blocked` is the inbox or the
    run record being unreachable, which is why it is recorded apart from it.
    """

    status: str = ""
    proposals: int = 0
    top_layer: str = ""
    notes: str = ""


class ImprovementsRecorded(CoderResult):
    """`record-improvements.py` — the inbox drained into the ledger.

    `added` are proposals seen for the first time; `bumped` are ones already in the ledger
    whose observation count went up. A proposal observed across many runs is the signal
    the ledger exists to produce, so the two are counted apart.

    The script emitted a `note` key on the empty-inbox path and an `error` key on the
    unreadable-inbox one, both purely descriptive. They are one `note` field here: the two
    keys were never read apart, and a second field would only invite a branch on which of
    them is set.
    """

    added: int = 0
    bumped: int = 0
    ledger: str = ""
    total: int = 0
    note: str = ""


__all__ = ["ImprovementsRecorded", "ReflectionResult", "RunEvidence"]
