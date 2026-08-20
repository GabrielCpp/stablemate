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
no story in scope (`dream-reflect`) must not emit a dangling `Story:` line, and the guard
that prevents it is Jinja, which a grep cannot evaluate.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse.templates import render

import workhorse_workflows

PROMPTS = Path(workhorse_workflows.__file__).parent / "coder" / "prompts"

HEADING = "## Commit What You Wrote"

#: Prompts whose deliverable is a file in the repo. Each must carry the instruction.
PRODUCERS = {
    "apply-qa-fixes.md",
    "apply-review.md",
    "audit-qa.md",
    "document-story.md",
    "dream-reflect.md",
    "fix-regression.md",
    "implement-plan.md",
    "plan-qa.md",
    "plan-story.md",
    "qa-fix-item.md",
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

#: Prompts that write nothing a commit could carry: two reviewers that are told in so
#: many words not to commit, a documentation review that only reports, two reporters that
#: write to a ticket, and the operator gate (whose file is the gate, not the repo).
NON_PRODUCERS = {
    "code-review.md",
    "code-reuse.md",
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
    return {p.name for p in PROMPTS.glob("*.md")}


def test_every_prompt_is_classified() -> None:
    """A new prompt is a decision, not a default."""
    classified = PRODUCERS | SELF_COMMITTING | NON_PRODUCERS
    assert _all_prompts() == classified


@pytest.mark.parametrize("name", sorted(PRODUCERS))
def test_producer_carries_the_commit_instruction(name: str) -> None:
    body = (PROMPTS / name).read_text(encoding="utf-8")
    assert HEADING in body
    section = body.split(HEADING, 1)[1]
    assert "git add -A" in section, "the explicit-path rule names what it forbids"
    assert "Do not push" in section


@pytest.mark.parametrize("name", sorted(PRODUCERS))
def test_trailers_render_from_the_turn_args(name: str) -> None:
    context = {"story_slug": "STORY-1-widget", "epic": "EPIC-2-checkout"}
    section = _commit_section(render(PROMPTS / name, context, PROMPTS.parent))
    assert "Epic: EPIC-2-checkout" in section
    assert "Story: STORY-1-widget" in section


@pytest.mark.parametrize("name", sorted(PRODUCERS))
def test_trailers_vanish_when_there_is_no_story(name: str) -> None:
    """`dream-reflect` runs with no story in scope; a bare `Story:` would be a lie."""
    section = _commit_section(render(PROMPTS / name, {}, PROMPTS.parent))
    assert "Epic:" not in section
    assert "Story:" not in section
