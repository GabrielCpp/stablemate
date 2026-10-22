"""Typed inputs and results for the epic-split flow."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from workhorse.pyflow import dry_run


class EpicSplitContext(BaseModel):
    """The approved milestone and graph snapshot that bound the split turn."""

    repo_root: str = ""
    epics_dir: str = ""
    milestone_path: str = ""
    existing_epics: list[str] = Field(default_factory=list)
    milestone_fingerprints: dict[str, str] = Field(default_factory=dict)
    epic_fingerprints: dict[str, str] = Field(default_factory=dict)
    seed_ids: dict[str, list[str]] = Field(default_factory=dict)
    story_slugs: dict[str, list[str]] = Field(default_factory=dict)
    pm_ledger: str = ""


@dry_run(status="complete", notes="")
class EpicSplitResult(BaseModel):
    """A split or rework turn's reply."""

    status: Literal["complete", "blocked"]
    notes: str


@dry_run(ok=True)
class EpicSplitValidation(BaseModel):
    """Mechanical evidence that the output is skeleton-only and ordered by the milestone."""

    ok: bool = False
    milestone_path: str = ""
    ordered_epics: list[str] = Field(default_factory=list)
    errors: str = ""


class EpicSplitDone(BaseModel):
    """The epic split's outcome: accepted by the lint and the PM, or blocked with the reason."""

    status: Literal["accepted", "blocked"] = "accepted"
    milestone_path: str = ""
    ordered_epics: list[str] = Field(default_factory=list)
    notes: str = ""
    reworks: int = 0
    answers: int = 0


__all__ = [
    "EpicSplitContext",
    "EpicSplitDone",
    "EpicSplitResult",
    "EpicSplitValidation",
]
