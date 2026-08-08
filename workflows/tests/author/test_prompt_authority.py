"""Author prompts agree on who may decide previously unspecified behavior."""
from __future__ import annotations

from pathlib import Path

import workhorse_workflows

PROMPTS = Path(workhorse_workflows.__file__).parent / "author" / "prompts"


def _prompt(name: str) -> str:
    return " ".join((PROMPTS / name).read_text(encoding="utf-8").split())


def test_writer_can_define_in_scope_behavior_without_prior_okf_authority() -> None:
    text = _prompt("write-story.md")

    assert "Acceptance Criteria become the authoritative contract" in text
    assert "Absence from the existing OKF book is not by itself a reason to block" in text
    assert "must not contradict existing documented behavior" in text


def test_auditor_does_not_demand_prior_citations_for_new_behavior() -> None:
    text = _prompt("audit-story.md")

    assert "Do not refute new in-scope behavior merely because no prior OKF node defines it" in text
    assert "contradicts cited existing behavior" in text


def test_reworker_makes_in_scope_choices_instead_of_blocking() -> None:
    text = _prompt("rework-story.md")

    assert "make the concrete choice in the Acceptance Criteria" in text
    assert "Do not block merely because the existing OKF book is silent" in text
