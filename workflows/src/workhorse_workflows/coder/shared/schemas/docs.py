"""The docs flow's models: the spec author, the book gate, the verdict."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult


@dry_run(status="documented")
class SpecResult(CoderResult):
    """`docs/prompts/specify-story.md` — the story's behaviour model and the book delta it implies, before any code."""

    status: Literal["documented", "not_required", "blocked"] = Field(
        description="`documented` when model.md is written and `ostler book check` exits 0 for every service "
        "of the story. "
        "`not_required` when the story changes no observable behaviour, with the reason in "
        "`notes`. `blocked` when a cell needs a product decision that is not yours, named in "
        "`notes`.",
    )
    notes: str = Field(
        default="",
        description="What you decided and why, in one or two sentences, or the reason the "
        "story needs no book change, or the decision that blocks you.",
    )


class SpecBookPaths(CoderResult):
    """`record_spec_book_paths` — the book paths the spec pass wrote, kept for the lanes after it."""

    book_paths: list[str] = []


@dry_run(status="passed")
class DocumentationGate(CoderResult):
    """`verify-story-documentation.py` — the fail-closed conformance and grounding gate."""

    status: Literal["passed", "invalid"] = "invalid"
    notes: str = ""
    failures: list[str] = []


DocsStatus = Literal["passed", "not_applicable", "blocked", "failed"]


class DocsResult(CoderResult):
    """What the docs flow hands back: `passed`, `not_applicable` or `blocked`."""

    status: DocsStatus = "failed"
    notes: str = ""


__all__ = [
    "DocsStatus",
    "DocsResult",
    "DocumentationGate",
    "SpecBookPaths",
    "SpecResult",
]
