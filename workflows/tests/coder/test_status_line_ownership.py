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

The dev lane no longer argues the point at length: `check_story_status` re-reads the line
after every implementing and repairing turn and routes a violation back through the repair
budget, so the prompt states the rule once and the gate is what makes stating it binding.
The assertion here is about *forbidding*, not about phrasing — rewording is fine, deleting
the prohibition is the regression.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import workhorse_workflows
from workhorse_workflows.coder.shared.schemas.dev import StoryStatusCheck

CODER = Path(workhorse_workflows.__file__).parent / "coder"

#: The prompts that change code but hold no status verdict. `review-implementation`,
#: `apply-qa-fixes` and `replan-epic` are absent on purpose — each one *does* own a
#: transition and is told to write it.
NO_STATUS_AUTHORITY = ("implement-plan.md", "apply-review.md")

#: Every copy of them. `implement-plan` is duplicated across the flows that render it,
#: and the guard has to hold in each — the copies are free to diverge, which is exactly
#: how one of them would lose the prohibition unnoticed.
UNAUTHORIZED = sorted(
    p for p in CODER.glob("*/prompts/*.md") if p.name in NO_STATUS_AUTHORITY
)

#: Ways of saying "not yours to write". A prompt satisfies the rule with any one of them;
#: the list grows when a prompt finds a better sentence, never when one drops the rule.
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
    """Each prompt points at the machinery that re-reads the line, not at a bare rule.

    The agent that stamped `QA passed` was not being careless — it had genuinely re-verified
    the story and was recording a true-looking fact. A prohibition with nothing behind it
    reads as bookkeeping to an agent in that position. `implement-plan` names the gate that
    re-reads the line; `apply-review` names the gate that owns the transition instead.
    """
    for prompt in UNAUTHORIZED:
        section = prompt.read_text(encoding="utf-8").partition("## Story Status")[2]
        assert "gate" in section, prompt


def test_the_dev_gate_defaults_to_dirty() -> None:
    """The claim the prompt makes is only true because this node exists and fails closed.

    An unbuilt check has verified nothing, so its default is the arm that loops the turn.
    """
    assert StoryStatusCheck().status == "dirty"
