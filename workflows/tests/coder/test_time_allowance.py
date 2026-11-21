"""Every owner prompt tells its turn the minutes it has before the run cuts it."""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner
from workhorse.runner.spec import AgentNode

from workhorse_workflows import coder

OWNER_PROMPTS = {
    "dev-plan": "dev/prompts/dev-plan.md",
    "dev-build": "dev/prompts/dev-build.md",
    "dev-review": "dev/prompts/dev-review.md",
    "dev-follow-up": "dev/prompts/dev-follow-up.md",
    "qa": "qa/prompts/qa-story.md",
    "book-qa": "book_qa/prompts/qa-book.md",
    "book-qa-review": "book_qa/prompts/qa-review.md",
    "docs": "docs/prompts/specify-story.md",
    "fix": "fix/prompts/fix-item.md",
    "fix-ci": "fix_ci/prompts/fix-ci.md",
    "fix-merge": "fix_ci/prompts/fix-merge.md",
}


def _render(prompt: str, timeout: float) -> str:
    node = AgentNode(type="agent", id="owner", prompt=prompt, timeout=timeout)
    turn = AgentRunner(backend=NullBackend()).render(node, {}, Path(coder.__file__).parent)
    return turn.prompt


@pytest.mark.parametrize("prompt", OWNER_PROMPTS.values(), ids=OWNER_PROMPTS.keys())
def test_an_owner_prompt_states_its_time_allowance(prompt: str) -> None:
    assert "This turn has 7 minutes" in _render(prompt, 420.0)


@pytest.mark.parametrize("prompt", OWNER_PROMPTS.values(), ids=OWNER_PROMPTS.keys())
def test_an_unbounded_turn_states_no_time_allowance(prompt: str) -> None:
    assert "Time allowance" not in _render(prompt, float("inf"))
