"""The docs flow's models: the OKF pre-gate, the context classifier, the author, the gates."""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding
from workhorse_workflows.kit.telemetry import ProgressVerdict, progress_verdict


class OkfDetection(CoderResult):
    """`detect-okf-docs.py` — are this repo's docs managed by an OKF graph at all?"""

    has_okf: Literal["yes", "no", "invalid"] = "no"
    features_root: str = ""
    reason: str = ""


class ContextClassification(CoderResult):
    """`classify-documentation-context.py` — deterministic diff mapping, or semantic review?"""

    mode: Literal["local", "semantic", "error"] = "semantic"
    source_roots: list[str] = []
    notes: str = ""


class WorktreeSnapshot(CoderResult):
    """What was already dirty in the repo when this story started."""

    entries: list[str] = []
    notes: str = ""


class DocumentationResult(CoderResult):
    """`docs/prompts/document-story.md` — the story folded into the as-built OKF book."""

    status: Literal["documented", "not_required", "blocked"] = Field(
        description="`documented` when the current contracts are updated and `doctor` "
        "reports no error on the affected nodes. `not_required` needs both a precise "
        "explanation of why no observable contract changed and that every changed "
        "production file was already directly grounded — a grounding bullet you had to add "
        "makes the answer `documented`. `blocked` when the book cannot be made true of "
        "this code without a decision that is not yours.",
    )
    nodes: list[str] = Field(
        default=[],
        description="Every OKF node you edited, by exact graph identity with its section "
        "anchor preserved. Empty for `not_required`.",
    )
    notes: str = Field(
        default="",
        description="What you changed and why, in one or two sentences. Report unrelated "
        "pre-existing doctor findings here rather than rewriting unrelated books.",
    )


class DocumentationGate(CoderResult):
    """`verify-story-documentation.py` — the fail-closed conformance and grounding gate."""

    status: Literal["passed", "invalid"] = "invalid"
    notes: str = ""
    changed_code_count: int = 0
    doctor_error_count: int = 0
    failures: list[str] = []


class DocumentationObligations(CoderResult):
    """`documentation_obligations` — the grounding worklist handed to the author up front."""

    refs: list[str] = []
    notes: str = ""


class DocumentationFinding(Finding):
    """One semantic documentation review finding handed back to the author."""

    id: str = Field(
        default="",
        description="A stable handle for this finding — `D1`, `D2` — reused when you "
        "restate it on a later pass.",
    )
    kind: Literal[
        "node-type",
        "missing-node",
        "flow-coverage",
        "overclaim",
        "bullet-granularity",
        "grounding",
        "verify-overclaim",
        "author-decision",
    ] = Field(description="What class of defect this is, so the repair can be routed.")


class DocumentationReview(CoderResult):
    """`docs/prompts/review-story-documentation.md` — an independent read of what was written."""

    status: Literal["approved", "revise", "blocked"] = Field(
        description="`revise` only with at least one structured finding. `blocked` only "
        "when convergence needs a product or author decision. Never approve on the promise "
        "of a later documentation update.",
    )
    findings: list[DocumentationFinding] = Field(
        default=[],
        description="The repair contract the author works from — empty on `approved`.",
    )
    notes: str = Field(
        default="",
        description="A one or two sentence summary; the findings list, not this, is what "
        "the author repairs from.",
    )


class DocsProgress(CoderResult):
    """What each gate last decided, and whether the rework it forced was worth spending."""

    gate_verdict: Literal["", "passed", "invalid"] = ""
    review_disposition: Literal["", "approved", "revise", "blocked"] = ""
    gate_progress_verdict: ProgressVerdict | Literal[""] = ""
    review_progress_verdict: ProgressVerdict | Literal[""] = ""

    gate_failures: int = 0
    review_findings: int = 0

    gate_ids: list[str] = []
    review_ids: list[str] = []

    chain_laps: int = 0

    VERDICT_LABELS: ClassVar[tuple[str, ...]] = (
        "gate_verdict",
        "review_disposition",
        "gate_progress_verdict",
        "review_progress_verdict",
    )

    COUNT_LABELS: ClassVar[tuple[str, ...]] = ("gate_failures", "review_findings")

    def after_gate(self, gate: DocumentationGate) -> DocsProgress:
        """Record what the deterministic grounding gate just decided."""
        ids = list(gate.failures)
        return self.model_copy(
            update={
                "gate_verdict": gate.status,
                "gate_failures": len(ids),
                "gate_progress_verdict": progress_verdict(self.gate_ids or None, ids),
                "gate_ids": ids,
            }
        )

    def after_review(self, review: DocumentationReview) -> DocsProgress:
        """Record what the semantic reviewer just decided."""
        ids = [finding.id for finding in review.findings] if review.status == "revise" else []
        return self.model_copy(
            update={
                "review_disposition": review.status,
                "review_findings": len(ids),
                "review_progress_verdict": progress_verdict(self.review_ids or None, ids),
                "review_ids": ids,
            }
        )


class DocsLoop(BaseModel):
    """Everything one documentation pass carries into the next, as one state parameter."""

    rework: int = 0

    review_rework: int = 0

    blocks: int = 0

    gate_notes: str = ""
    review_notes: str = ""

    obligations: tuple[str, ...] = ()

    authored_nodes: tuple[str, ...] = ()

    progress: DocsProgress = Field(default_factory=DocsProgress)

    overruns: int = 0

    COUNT_LABELS: ClassVar[tuple[str, ...]] = (
        "rework",
        "review_rework",
        "blocks",
        "overruns",
    )


class RepairOverran(BaseModel):
    """What a repair turn cut at its wall-clock budget leaves in the checkpoint."""

    status: Literal["overran"] = "overran"

    lap: int = 0

    notes: str = ""


DocsStatus = Literal["passed", "not_applicable", "blocked", "failed"]


class DocsResult(CoderResult):
    """What the docs flow hands back: `passed`, `not_applicable` or `blocked`."""

    status: DocsStatus = "failed"
    notes: str = ""
    authored_nodes: list[str] = []


__all__ = [
    "ContextClassification",
    "DocsLoop",
    "DocsStatus",
    "DocsProgress",
    "DocsResult",
    "DocumentationFinding",
    "DocumentationGate",
    "DocumentationResult",
    "DocumentationReview",
    "OkfDetection",
    "RepairOverran",
    "WorktreeSnapshot",
]
