"""Values owned by the standalone story-author flow."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas import AuthorResult


class StoryTarget(AuthorResult):
    """The explicit story, after its document was given any required section it lacked."""

    epic: str = ""
    story: str = ""
    story_id: str = ""
    epic_dir: str = ""
    story_dir: str = ""
    story_path: str = ""
    scaffolded: bool = False
    scaffold_message: str = ""


class StoryAuthorDone(AuthorResult):
    """A directly invoked story-author run passed all its gates, or stays blocked with a question."""

    status: str = "authored"
    epic: str = ""
    story: str = ""
    story_path: str = ""
    mockup: str = ""
    notes: str = ""
    reworks: int = 0
    answers: int = 0


__all__ = ["StoryAuthorDone", "StoryTarget"]
