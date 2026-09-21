"""The pre-QA implementation prompts must forbid hand-editing the story's status line."""
from __future__ import annotations

from pathlib import Path

import pytest

import workhorse_workflows
from workhorse_workflows.coder.shared.schemas.dev import StoryStatusCheck

CODER = Path(workhorse_workflows.__file__).parent / "coder"

NO_STATUS_AUTHORITY = ("implement-plan.md", "apply-review.md")

UNAUTHORIZED = sorted(
    p for p in CODER.glob("*/prompts/*.md") if p.name in NO_STATUS_AUTHORITY
)

PROHIBITIONS = ("Do **not**", "do **not**", "exactly as you found them")


def _id(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.stem}"


@pytest.mark.parametrize("prompt", UNAUTHORIZED, ids=_id)
def test_the_prompt_forbids_writing_the_story_status_line(prompt: Path) -> None:
    """Each names the status line and prohibits editing it."""
    text = prompt.read_text(encoding="utf-8")
    section = text.partition("## Story Status")[2]
    assert section, f"{prompt} has no `## Story Status` section"
    assert "Implementation Status" in section, prompt
    assert any(phrase in section for phrase in PROHIBITIONS), prompt


def test_the_guard_names_what_enforces_it() -> None:
    """Each prompt points at the machinery that re-reads the line, not at a bare rule."""
    for prompt in UNAUTHORIZED:
        section = prompt.read_text(encoding="utf-8").partition("## Story Status")[2]
        assert "gate" in section, prompt


def test_the_dev_gate_defaults_to_dirty() -> None:
    """The claim the prompt makes is only true because this node exists and fails closed."""
    assert StoryStatusCheck().status == "dirty"
