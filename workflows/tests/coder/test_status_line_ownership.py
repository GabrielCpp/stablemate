"""The pre-QA implementation prompts must forbid hand-editing the story's status line.

A story's status is the queue's source of truth: `ostler.select.is_done` matches `qa passed`,
`done`, `merged` and `complete` as substrings, so whatever sits on that line decides whether
the story is ever selected again. Only the gates that hold a structured verdict may write it.

A live benchmark run showed what happens when an implementation prompt does not say so.
`implement-plan` was re-verifying `expense-record`, a story carrying a QA give-up from an
earlier run. It did the verification, decided the fix held, and stamped
`status: QA passed` on the story — during **dev**, three phases before QA ran. Had that run
then crashed, or set the epic aside (which is exactly how the story got its give-up in the
first place), the story would have stayed "passed" forever without any QA the workflow itself
performed. `apply-review.md` already carried this guard; `implement-plan.md` did not, and the
asymmetry was invisible until an agent took the opening.

The assertion is deliberately about *forbidding*, not about phrasing: it checks that each
prompt names the status line and tells the agent not to write it. Rewording the section is
fine; deleting the prohibition is the regression.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import workhorse_workflows

PROMPTS = Path(workhorse_workflows.__file__).parent / "coder" / "prompts"

#: The prompts that change code but hold no status verdict. `review-implementation`,
#: `apply-qa-fixes` and `replan-epic` are absent on purpose — each one *does* own a
#: transition and is told to write it.
NO_STATUS_AUTHORITY = ("implement-plan.md", "apply-review.md")


@pytest.mark.parametrize("name", NO_STATUS_AUTHORITY)
def test_the_prompt_forbids_writing_the_story_status_line(name: str) -> None:
    """Each names the status line and prohibits editing it."""
    text = PROMPTS.joinpath(name).read_text(encoding="utf-8")
    section = text.partition("## Story Status")[2]
    assert section, f"{name} has no `## Story Status` section"
    assert "Implementation Status" in section, name
    assert "Do **not**" in section or "do **not**" in section, name


def test_the_guard_explains_why_a_stamped_status_sticks() -> None:
    """`implement-plan` says what a premature stamp costs, not just that it is banned.

    The agent that stamped `QA passed` was not being careless — it had genuinely re-verified
    the story and was recording a true-looking fact. A bare prohibition reads as bookkeeping
    to an agent in that position; the consequence is what makes it a rule worth obeying.
    """
    section = (
        PROMPTS.joinpath("implement-plan.md")
        .read_text(encoding="utf-8")
        .partition("## Story Status")[2]
    )
    assert "QA passed" in section
    assert "queue" in section
