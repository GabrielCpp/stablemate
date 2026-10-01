"""What the author's deterministic gates return under `--dry-run`."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas.main import Defects, VerifyReport


def clean(*_args: object, **_kwargs: object) -> Defects:
    """`validate_story`, `check_story_grounding`, `validate_coverage`, `validate_artifacts` — nothing wrong with what the run wrote."""
    return Defects(ok=True)


def holds(*_args: object, **_kwargs: object) -> VerifyReport:
    """`verify_reconcile`, `verify_integrity` — the graph reconciles and links up."""
    return VerifyReport(holds=True)


__all__ = ["clean", "holds"]
