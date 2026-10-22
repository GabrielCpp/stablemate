"""Typed terminal values for the standalone story-split flow."""
from typing import Literal

from workhorse_workflows.author.shared.schemas import AuthorResult


class StorySplitDone(AuthorResult):
    """One epic's story graph passed the lint and the PM review, or stays blocked."""

    status: Literal["accepted", "blocked"] = "accepted"
    epic: str
    epic_dir: str
    notes: str = ""
    reworks: int = 0
    answers: int = 0


class StoryServices(AuthorResult):
    """The `services:` written into each story of one epic, by story slug."""

    epic: str = ""
    services: dict[str, list[str]] = {}


__all__ = ["StoryServices", "StorySplitDone"]
