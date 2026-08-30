"""Author prompts agree on who may decide previously unspecified behavior.

Each flow owns its own copy of the envelopes it renders, so `write-story`, `audit-story`
and `rework-story` each exist twice over — once under `main/prompts/` and once under
`epic_edit/prompts/`. The copies are free to diverge, which is exactly why this is
restated over every one of them: an agreement about *authority* that held in one copy and
not the other would be a story the two flows write to different contracts.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import workhorse_workflows

AUTHOR = Path(workhorse_workflows.__file__).parent / "author"
MAIN_PROMPTS = AUTHOR / "main" / "prompts"


def _copies(name: str) -> list[Path]:
    found = sorted(AUTHOR.glob(f"*/prompts/{name}"))
    assert found, f"no flow ships {name} — the glob is looking in the wrong place"
    return found


def _id(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.stem}"


def _prose(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


@pytest.mark.parametrize("prompt", _copies("write-story.md"), ids=_id)
def test_writer_can_define_in_scope_behavior_without_prior_okf_authority(prompt: Path) -> None:
    text = _prose(prompt)

    assert "Acceptance Criteria become the authoritative contract" in text
    assert "Absence from the existing OKF book is not by itself a reason to block" in text
    assert "must not contradict existing documented behavior" in text


@pytest.mark.parametrize("prompt", _copies("audit-story.md"), ids=_id)
def test_auditor_does_not_demand_prior_citations_for_new_behavior(prompt: Path) -> None:
    text = _prose(prompt)

    assert "Do not refute new in-scope behavior merely because no prior OKF node defines it" in text
    assert "contradicts cited existing behavior" in text


@pytest.mark.parametrize("prompt", _copies("audit-story.md"), ids=_id)
def test_auditor_respects_the_bare_minimum_story_boundary(prompt: Path) -> None:
    text = _prose(prompt)

    assert "Do not demand endpoint names, request or response schemas" in text
    assert "Judge only the behavior changed by this story's covered seeds" in text
    assert "does not import every guard, state, interaction, or journey" in text
    assert "Existing guards, chrome, states, and flows outside those covered seeds" in text


@pytest.mark.parametrize("prompt", _copies("rework-story.md"), ids=_id)
def test_reworker_makes_in_scope_choices_instead_of_blocking(prompt: Path) -> None:
    text = _prose(prompt)

    assert "make the concrete choice in the Acceptance Criteria" in text
    assert "Do not block merely because the existing OKF book is silent" in text


@pytest.mark.parametrize(
    "name",
    [
        "decompose-epics.md",
        "rework-epics.md",
        "write-epic.md",
        "split-stories.md",
        "write-story.md",
        "design-mockup.md",
        "audit-story.md",
        "rework-story.md",
        "resolve-integrity.md",
    ],
)
def test_mutating_turns_leave_validation_and_delivery_to_author(name: str) -> None:
    text = _prose(MAIN_PROMPTS / name)

    assert "do not install dependencies, run repository-wide checks" in text
    assert "stage, commit, push, or alter branches/remotes" in text
    assert "Author validates and delivers after all authoring turns finish" in text


def test_epic_review_does_not_inherit_unrelated_planning_debt() -> None:
    text = _prose(MAIN_PROMPTS / "review-epics.md")

    assert "validates the roadmap-owned planning subgraph mechanically" in text
    assert "Do not run repository-wide checks or inspect unrelated milestones" in text


def test_epic_writer_records_the_seed_set_without_per_seed_graph_reloads() -> None:
    text = _prose(MAIN_PROMPTS / "write-epic.md")

    assert "Write or refine the complete seed set in one edit" in text
    assert "do not launch a separate `ostler seed add` process per seed" in text
    assert "following the installed artifact grammar" in text
