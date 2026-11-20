"""What finalize's repair turn replies."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas._base import AuthorResult
from workhorse.pyflow import dry_run


@dry_run(decision="answered")
class OperatorResolution(AuthorResult):
    """`finalize/prompts/resolve-integrity.md` — the diagnostic investigator's report."""

    decision: str = ""
    notes: str = ""

    tried: list[str] = []


__all__ = ["OperatorResolution"]
