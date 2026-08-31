"""Values owned by the standalone story-author flow."""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas import AuthorResult


class StoryTarget(AuthorResult):
    """The explicit story, after its document was given any required section it lacked."""

    epic: str = ""
    story: str = ""
    epic_dir: str = ""
    story_dir: str = ""
    story_path: str = ""
    scaffolded: bool = False
    scaffold_message: str = ""


class StoryAuthorDone(AuthorResult):
    """A directly invoked story-author run completed all authoring gates."""

    status: str = "authored"
    epic: str = ""
    story: str = ""
    story_path: str = ""
    mockup: str = ""
    notes: str = ""


class AuditReceipt(AuthorResult):
    """Durable proof that the current story bytes passed the independent audit."""

    story_digest: str = ""
    path: str = ""


__all__ = ["AuditReceipt", "StoryAuthorDone", "StoryTarget"]
