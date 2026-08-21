"""`write-story.md` never demands an artifact another gate deterministically suppressed.

The story writer has two sibling gates in `author/nodes/stories.py`, and both of them
stand down on a greenfield backend-only story: `check_story_grounding` puts its
cite-a-node requirement behind `if okf.graph.ui_nodes:`, and `check_mockup_needed`
decides from `layers:` on the covered seeds, so a story tagged `layers: backend` gets
no `mockup_path` at all. The prompt is supposed to describe those gates. For one live
round it described a stricter pair: cite an OKF node, or link the mockup — and in a
repo whose book is not built yet, for a story that was correctly given no mockup, both
arms were empty. The author obeyed the prose over the prompt's own *Authority for new
behavior* clause ("Absence from the existing OKF book is not by itself a reason to
block"), found nothing linkable, and parked the round at the operator gate.

That is prose drift, and prose drift is invisible to ruff, to ty, and to review — the
template still renders, it just renders instructions no reachable repo can satisfy. So
the guard is a render: build the parameterization the gates actually produce for that
story (a book configured but empty, no mockup) and assert the third arm is present in
the text the author reads.
"""
from __future__ import annotations

from pathlib import Path

from workhorse.templates import render

import workhorse_workflows

WORKFLOW_DIR = Path(workhorse_workflows.__file__).parent / "author"


def _backend_only_story() -> dict[str, object]:
    """What the nodes hand the template for a backend story in an undocumented repo.

    `features_dir` is set — the book is configured, which is why the grounding block
    renders at all — and `mockup_path` is empty, because `check_mockup_needed` saw
    `layers: backend` on every covered seed and suppressed it.
    """
    return {
        "epic": "0001-example-api",
        "story_slug": "create-example",
        "story_path": "docs/epics/0001-example-api/stories/create-example/story.md",
        "story_dir": "docs/epics/0001-example-api/stories/create-example",
        "features_dir": "docs/okf",
        "mockup_path": "",
    }


def test_the_backend_only_story_is_given_something_to_ground_in() -> None:
    rendered = render("prompts/write-story.md", _backend_only_story(), WORKFLOW_DIR)

    # Not a bare "epic's seeds" — the *Authority for new behavior* section says those words
    # already, and an assertion that passes against the prose this test exists to replace is
    # no assertion. Match the instruction to ground in them.
    assert "Ground the Context in the epic's seeds this story `covers`" in rendered, (
        "a story with no book node and no mockup has only the epic's seeds to ground in; "
        "if the prompt does not say so it has told the author to link nothing that exists"
    )
    assert "new and undocumented" in rendered


def test_the_absent_mockup_is_not_a_block() -> None:
    """The park this test exists for was an author blocking on a missing artifact.

    Asserting the seeds are *mentioned* is not enough: the earlier prose mentioned the
    mockup too, as the thing to link. What must be present is the permission not to
    block on its absence.
    """
    rendered = render("prompts/write-story.md", _backend_only_story(), WORKFLOW_DIR)

    assert "its absence is not a block" in rendered
    assert "Do not block for the want of a node or a mockup" in rendered


def test_the_mockup_arm_survives_for_the_story_that_has_one() -> None:
    """The fix widens the disjunction; it must not have replaced the original arm."""
    context = _backend_only_story() | {"mockup_path": "./mockup.html"}

    rendered = render("prompts/write-story.md", context, WORKFLOW_DIR)

    assert "./mockup.html" in rendered
    assert "link it from Context as the source of truth" in rendered
