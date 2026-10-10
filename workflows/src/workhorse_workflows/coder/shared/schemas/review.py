"""The review models: a reviewer's finding, where review turns run, the feedback inbox."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding

ReviewCategory = Literal["Bug", "Standard", "Reuse"]


class ReviewFinding(Finding):
    """A code-review finding: the base contract, plus which lens caught it and how sure it is."""

    category: ReviewCategory = Field(
        description="Which lens caught it. `Reuse` covers both duplicated code and a missed "
        "utility; the implementation reviewer selects on it to report those separately.",
    )

    score: int = Field(
        default=0,
        description="The 0-100 confidence you scored it. Report every finding you scored, "
        "whatever it scored: the flow splits the list on this number, so a low score demotes "
        "a finding to advisory context, while one you drop yourself reaches nobody.",
    )


class ReviewContext(CoderResult):
    """`resolve-review-context.py` — where the review turns run, and what they may read."""

    docs_repo_path: str = ""
    affected_repo_paths: list[str] = []


class Feedback(CoderResult):
    """`check_feedback` — an un-consumed operator note dropped into the run's inbox."""

    present: bool = False
    content: str = ""


__all__ = [
    "Feedback",
    "ReviewCategory",
    "ReviewContext",
    "ReviewFinding",
]
