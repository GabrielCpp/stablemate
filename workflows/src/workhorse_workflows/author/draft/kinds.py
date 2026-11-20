"""What differs between the documents the draft loop writes: prompts, reply, review stage and labels."""
from __future__ import annotations

from dataclasses import dataclass

from workhorse_workflows.author.epic_split.schemas import EpicSplitResult
from workhorse_workflows.author.shared.schemas import StorySplit, WriteStoryResult

type Reply = EpicSplitResult | StorySplit | WriteStoryResult

WRITE = {
    "epic-split": "epic_split/prompts/split-epics.md",
    "story-split": "story_split/prompts/split-stories.md",
    "story": "story_author/prompts/write-story.md",
    "edited-story": "epic_edit/prompts/write-story.md",
}

REWORK = {
    "epic-split": "epic_split/prompts/rework-epic-split.md",
    "story-split": "story_split/prompts/split-stories.md",
    "story": "story_author/prompts/rework-story.md",
    "edited-story": "epic_edit/prompts/rework-story.md",
}


@dataclass(frozen=True)
class Kind:
    """One kind of document.

    `returns` is the shape of a write or rework reply, `stage` the PM review stage, `asker`
    the name the PM's ledger records a question under, and `counter` the prefix of the
    loop's budget labels. A reply whose status is in `blocked` asks the PM a question.
    """

    returns: type[Reply]
    stage: str
    asker: str
    counter: str
    progress: str
    blocked: frozenset[str] = frozenset({"blocked"})


KINDS = {
    "epic-split": Kind(EpicSplitResult, "epic-split", "epic-split", "epic_split", "splitting the milestone into epics"),
    "story-split": Kind(
        StorySplit,
        "story-split",
        "story-split",
        "story_split",
        "splitting stories",
        frozenset({"blocked", "standoff"}),
    ),
    "story": Kind(WriteStoryResult, "story", "story-author", "story_author", "authoring one story"),
    "edited-story": Kind(WriteStoryResult, "story", "epic-edit", "epic_edit", "rewriting a story the edit touched"),
}

__all__ = ["KINDS", "REWORK", "WRITE", "Kind", "Reply"]
