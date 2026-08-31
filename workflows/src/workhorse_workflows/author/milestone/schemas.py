"""Typed inputs and results for the milestone flow."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MilestoneContext(BaseModel):
    """Validated roadmap identity and the planning graph before the authoring turn."""

    repo_root: str
    roadmap: str
    epics_dir: str
    milestone_path: str = ""
    milestone_epics: list[str] = Field(default_factory=list)
    milestone_fingerprints: dict[str, str] = Field(default_factory=dict)
    epic_fingerprints: dict[str, str] = Field(default_factory=dict)


class MilestoneResult(BaseModel):
    """The milestone authoring turn's machine-readable reply."""

    status: Literal["complete", "blocked"]
    notes: str


class MilestoneValidation(BaseModel):
    """Deterministic proof that this stage changed only one milestone document."""

    ok: bool = False
    milestone_path: str = ""
    reused: bool = False
    errors: str = ""


__all__ = ["MilestoneContext", "MilestoneResult", "MilestoneValidation"]
