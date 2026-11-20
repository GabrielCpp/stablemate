from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import CreateEpic, CreateStory, DeleteCreatedEpic, DeleteEpic, DeleteStory, Look, PathBranch, PathSpec, PathStory, UpdateStory
from ..fixtures import ALPHA, BRAVO, create_epic, create_story, delete_epic, delete_story, path_branch, path_spec, path_story, update_story


class ReshapeThePlan(Journey):
    """A planner grows the plan and trims it. They create a fourth epic, give it a story, retitle and relink the first
    epic's stories, find where a story and its spec live and which branch it takes, delete a story, and delete the
    new epic, which a story can no longer be filed under, and the second epic. They name the new epic by its
    slug and by an old NNNN-slug name, because the book cannot know the id the tool minted."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            CreateEpic(create_epic("fourth", "Fourth epic")),
            Look(),
            CreateStory(create_story("fourth", "delta")),
            CreateStory(create_story("0004-fourth", "delta")),
            Look(),
            UpdateStory(update_story(ALPHA, "Renamed alpha", "SD-3", "bravo")),
            UpdateStory(update_story(BRAVO, "Renamed bravo", "SD-4", "alpha")),
            Look(),
            PathStory(path_story(ALPHA)),
            PathSpec(path_spec(ALPHA)),
            PathBranch(path_branch(ALPHA)),
            PathBranch(path_branch("fourth", epic=True)),
            UpdateStory(update_story(ALPHA, "Story alpha", "(none)", "(none)")),
            Look(),
            DeleteStory(delete_story(BRAVO)),
            Look(),
            DeleteCreatedEpic(delete_epic("fourth")),
            CreateStory(create_story("fourth", "delta")),
            DeleteEpic(delete_epic("0002-second")),
            Look(),
        )
