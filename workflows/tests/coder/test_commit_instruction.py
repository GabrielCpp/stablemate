"""Every coder prompt that writes a file tells the agent to commit what it wrote.

The workflow stopped committing on the agent's behalf: `check_repos_clean` sits where
`commit_story` used to, so work left in the working tree when a story ends parks that
story for an operator instead of shipping it. That moved the obligation into the prompts,
and an obligation that lives in nineteen files is one a single edit can silently drop —
hence this sweep rather than trust.

Membership is spelled out both ways on purpose. `PRODUCERS` is what must carry the
instruction; `NON_PRODUCERS` is what must not be expected to (a reviewer that writes
nothing, a reporter that only comments on a ticket, the operator gate); and the two must
together account for every file in the directory, so a *new* prompt fails here until
somebody has decided which it is. A one-sided list would let a new producer ship with no
instruction and nothing red.

The trailers are rendered rather than grepped, because they are conditional: a turn with
no story in scope must not emit a dangling `Story:` line, and the guard that prevents it
is Jinja, which a grep cannot evaluate.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse.templates import render

import workhorse_workflows

CODER = Path(workhorse_workflows.__file__).parent / "coder"

#: Every envelope the coder workflow ships, across the flow packages that own them. A
#: duplicated stem is checked once per copy, which is the point: two copies of
#: `implement-plan.md` are two files and either can lose the instruction on its own.
PROMPTS = sorted(CODER.glob("*/prompts/*.md"))

HEADING = "## Commit What You Wrote"

#: Prompts whose deliverable is a file in the repo. Each must carry the instruction.
PRODUCERS = {
    "apply-qa-fixes.md",
    "apply-review.md",
    "audit-qa.md",
    "document-story.md",
    "fix-regression.md",
    "implement-plan.md",
    "plan-qa.md",
    "plan-story.md",
    "qa-fix-item.md",
    "fix-qa-scenario.md",
    "qa-story.md",
    "refine-plan.md",
    "repair-documentation.md",
    "repair-qa-context.md",
    "repair-qa-plan.md",
    "replan-epic.md",
    "review-implementation.md",
    "setup-fix.md",
    "triage-qa.md",
}

#: Prompts that already carried a commit instruction of their own before this section
#: existed — a fix lane commits per lap, and the settle prompt exists *because* a story
#: ended dirty. They are producers; they are simply not this section's shape.
SELF_COMMITTING = {
    "dev-fix.md",
    "fix-ci.md",
    "fix-merge.md",
    "settle-worktree.md",
}

#: Prompts that produce a file and carry **no** commit block, because the protocol is not
#: theirs to state: the target repo installs the `commit-and-push` policy through its own
#: generated agent instructions, and the turn-specific trailers are applied by the flow.
#: Every prompt written after that ruling belongs here; the ones above predate it.
REPO_OWNED = {
    "fix-item.md",
}

#: Prompts that write nothing a commit could carry: a reviewer that is told in so many
#: words not to commit, a documentation review that only reports, two reporters that
#: write to a ticket, and the operator gate (whose file is the gate, not the repo).
NON_PRODUCERS = {
    "code-review.md",
    "report-qa-dev-pass.md",
    "report-qa-dev.md",
    "resolve-operator.md",
    "review-story-documentation.md",
}


def _commit_section(rendered: str) -> str:
    """The instruction alone. `Epic:` is ordinary vocabulary elsewhere in these prompts."""
    assert HEADING in rendered
    return rendered.split(HEADING, 1)[1]


def _all_prompts() -> set[str]:
    return {p.name for p in PROMPTS}


def _producers() -> list[Path]:
    return [p for p in PROMPTS if p.name in PRODUCERS]


def _id(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.stem}"


def test_every_prompt_is_classified() -> None:
    """A new prompt is a decision, not a default."""
    classified = PRODUCERS | SELF_COMMITTING | REPO_OWNED | NON_PRODUCERS
    assert _all_prompts() == classified


@pytest.mark.parametrize("prompt", _producers(), ids=_id)
def test_producer_carries_the_commit_instruction(prompt: Path) -> None:
    body = prompt.read_text(encoding="utf-8")
    assert HEADING in body
    section = body.split(HEADING, 1)[1]
    assert "git add -A" in section, "the explicit-path rule names what it forbids"
    assert "Do not push" in section


@pytest.mark.parametrize("prompt", _producers(), ids=_id)
def test_trailers_render_from_the_turn_args(prompt: Path) -> None:
    context = {"story_slug": "STORY-1-widget", "epic": "EPIC-2-checkout"}
    section = _commit_section(render(prompt, context, CODER))
    assert "Epic: EPIC-2-checkout" in section
    assert "Story: STORY-1-widget" in section


@pytest.mark.parametrize("prompt", _producers(), ids=_id)
def test_trailers_vanish_when_there_is_no_story(prompt: Path) -> None:
    """A turn can run with no story in scope; a bare `Story:` would be a lie."""
    section = _commit_section(render(prompt, {}, CODER))
    assert "Epic:" not in section
    assert "Story:" not in section
