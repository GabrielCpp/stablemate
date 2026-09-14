"""The QA evidence gate node — a thin `@blueprint.node` wrapper.

The check itself — parsing `qa-evidence.json`, validating criteria, obligations,
parity/data-entry/transient proof, visual-fidelity reports, and the run manifest —
lives in `workhorse_workflows.qa.evidence.verify_qa_evidence`, a plain function shared
with any other family that needs to fail closed on the same evidence contract. This
wrapper keeps the node's name, checkpoint and telemetry unchanged.
"""
from __future__ import annotations

import logging

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.qa import QaResult
from workhorse_workflows.qa import evidence as _qa_evidence


@blueprint.node
def verify_qa_evidence(
    logger: logging.Logger,
    spec_dir: str = "",
    claimed_status: str = "",
    claimed_notes: str = "",
    repo_dir: str = "",
) -> QaResult:
    """Check a claimed QA pass against the proof on disk; downgrade to `invalid` if it lies."""
    return _qa_evidence.verify_qa_evidence(
        logger,
        spec_dir=spec_dir,
        claimed_status=claimed_status,
        claimed_notes=claimed_notes,
        repo_dir=repo_dir,
    )


__all__ = ["verify_qa_evidence"]
