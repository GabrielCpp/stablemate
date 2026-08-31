"""Typed terminal values for the standalone story-split flow."""
from typing import Literal

from workhorse_workflows.author.shared.schemas import AuthorResult


class StorySplitDone(AuthorResult):
    """One epic's story graph passed mechanical and semantic coverage review."""

    status: Literal["accepted"] = "accepted"
    epic: str
    epic_dir: str
    receipt_path: str
    coverage_reworks: int = 0
    operator_resolutions: int = 0


class StorySplitReceipt(AuthorResult):
    """A semantic review bound to the exact current story topology."""

    graph_digest: str
    path: str


__all__ = ["StorySplitDone", "StorySplitReceipt"]
