"""`write-story.md` never demands an artifact another gate deterministically suppressed."""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse.templates import render

import workhorse_workflows

WORKFLOW_DIR = Path(workhorse_workflows.__file__).parent / "author"

WRITE_STORY = sorted(WORKFLOW_DIR.glob("*/prompts/write-story.md"))


def _id(path: Path) -> str:
    return path.parent.parent.name


def _backend_only_story() -> dict[str, object]:
    """What the nodes hand the template for a backend story in an undocumented repo."""
    return {
        "epic": "0001-example-api",
        "story_slug": "create-example",
        "story_path": "docs/epics/0001-example-api/stories/create-example/story.md",
        "story_dir": "docs/epics/0001-example-api/stories/create-example",
        "features_dir": "docs/okf",
        "mockup_path": "",
    }


@pytest.mark.parametrize("prompt", WRITE_STORY, ids=_id)
def test_the_backend_only_story_is_given_something_to_ground_in(prompt: Path) -> None:
    rendered = render(prompt, _backend_only_story(), WORKFLOW_DIR)

    assert "Ground the Context in the epic's seeds this story `covers`" in rendered, (
        "a story with no book node and no mockup has only the epic's seeds to ground in; "
        "if the prompt does not say so it has told the author to link nothing that exists"
    )
    assert "new and undocumented" in rendered


@pytest.mark.parametrize("prompt", WRITE_STORY, ids=_id)
def test_the_absent_mockup_is_not_a_block(prompt: Path) -> None:
    """The park this test exists for was an author blocking on a missing artifact."""
    rendered = render(prompt, _backend_only_story(), WORKFLOW_DIR)

    assert "its absence is not a block" in rendered
    assert "Do not block for the want of a node or a mockup" in rendered


@pytest.mark.parametrize("prompt", WRITE_STORY, ids=_id)
def test_the_mockup_arm_survives_for_the_story_that_has_one(prompt: Path) -> None:
    """The fix widens the disjunction; it must not have replaced the original arm."""
    context = _backend_only_story() | {"mockup_path": "./mockup.html"}

    rendered = render(prompt, context, WORKFLOW_DIR)

    assert "./mockup.html" in rendered
    assert "link it from Context as the source of truth" in rendered
