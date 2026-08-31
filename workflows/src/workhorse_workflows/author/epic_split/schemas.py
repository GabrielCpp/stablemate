"""Typed inputs and results for the epic-split flow."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EpicSplitContext(BaseModel):
    """The roadmap milestone and graph snapshot that bound the split turn."""

    repo_root: str
    roadmap: str
    epics_dir: str
    milestone_path: str
    existing_epics: list[str] = Field(default_factory=list)
    milestone_fingerprints: dict[str, str] = Field(default_factory=dict)
    epic_fingerprints: dict[str, str] = Field(default_factory=dict)
    seed_ids: dict[str, list[str]] = Field(default_factory=dict)
    story_slugs: dict[str, list[str]] = Field(default_factory=dict)


class EpicSplitResult(BaseModel):
    """A split or rework turn's reply."""

    status: Literal["complete", "blocked"]
    notes: str


class EpicSplitReview(BaseModel):
    """The independent review verdict over the ordered skeletons."""

    status: Literal["approved", "needs_rework", "blocked"]
    notes: str


class EpicSplitValidation(BaseModel):
    """Mechanical evidence that the output is skeleton-only and ordered by the milestone."""

    ok: bool = False
    milestone_path: str = ""
    ordered_epics: list[str] = Field(default_factory=list)
    errors: str = ""


class OperatorResolution(BaseModel):
    """The diagnostic resolver's report before the flow parks for an operator."""

    decision: Literal["escalated"]
    notes: str
    tried: list[str] = Field(default_factory=list)


__all__ = [
    "EpicSplitContext",
    "EpicSplitResult",
    "EpicSplitReview",
    "EpicSplitValidation",
    "OperatorResolution",
]
