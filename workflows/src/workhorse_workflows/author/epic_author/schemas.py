"""Typed context and terminal values for the standalone epic-author flow."""
from __future__ import annotations

from typing import Literal

from workhorse_workflows.author.shared.schemas import AuthorResult, Config


class EpicTarget(AuthorResult):
    """The explicit epic resolved through Ostler without consulting a worklist."""

    epic: str = ""
    epic_dir: str = ""
    epic_path: str = ""


class EpicAuthorContext(Config):
    """Resolved config plus the one epic this run is allowed to author."""

    epic: str = ""
    epic_dir: str = ""
    epic_path: str = ""


class EpicEvidence(AuthorResult):
    """Ostler's evidence that the explicit epic has prose and durable seeds."""

    ok: bool = False
    epic: str = ""
    epic_dir: str = ""
    epic_path: str = ""
    seed_count: int = 0
    errors: str = ""


class EpicAuthorDone(AuthorResult):
    """One explicit epic completed its authoring boundary."""

    status: Literal["authored"] = "authored"
    epic: str = ""
    epic_dir: str = ""
    epic_path: str = ""
    seed_count: int = 0
    operator_resolutions: int = 0


__all__ = ["EpicAuthorContext", "EpicAuthorDone", "EpicEvidence", "EpicTarget"]
