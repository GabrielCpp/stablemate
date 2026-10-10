"""The docs flow's models: the OKF pre-gate, the context classifier, the author, the gates."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult


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


@dry_run(status="documented")
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


DocsStatus = Literal["passed", "not_applicable", "blocked", "failed"]


class DocsResult(CoderResult):
    """What the docs flow hands back: `passed`, `not_applicable` or `blocked`."""

    status: DocsStatus = "failed"
    notes: str = ""
    authored_nodes: list[str] = []


__all__ = [
    "ContextClassification",
    "DocsStatus",
    "DocsResult",
    "DocumentationGate",
    "DocumentationResult",
    "OkfDetection",
]
