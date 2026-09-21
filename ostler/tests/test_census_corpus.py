"""The census verdict, taken where it is sound: over every book of the corpus at once."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import census, doctor
from ostler.model import load

APPS = Path(__file__).resolve().parents[2] / "paddock" / "data" / "apps"


@pytest.fixture(scope="module")
def corpus() -> census.Census:
    """One census per app of the corpus, merged."""
    books = sorted(app for app in APPS.iterdir() if (app / "docs" / "features").is_dir())
    assert books, f"no corpus books under {APPS} — the gate below would pass vacuously"
    return census.merge(
        census.take_census(lambda graph=load(app): doctor.run(graph, check_schema=True))
        for app in books
    )


def test_the_corpus_enters_every_checker_a_profile_can_gate(corpus: census.Census) -> None:
    """The precondition of every other assertion here, asserted rather than assumed."""
    assert "full" in set(corpus.profile.split("+")), corpus.profile
    assert corpus.runs >= 2


def test_no_checker_is_unentered_by_the_whole_corpus_without_a_recorded_reason(
    corpus: census.Census,
) -> None:
    """The gate: a rule that stops being enforced must be a decision, not a thing that happened."""
    assert not corpus.undeclared, "\n".join(
        [""] + [f"  {code:40} {', '.join(sorted(corpus.sites.get(code, ())))}"
                for code in sorted(corpus.undeclared)])


def test_no_recorded_reason_outlives_the_code_it_excused(corpus: census.Census) -> None:
    """The other direction: a family wired back up must not leave its excuse to pre-waive the next."""
    assert not corpus.stale, "\n".join(
        [""] + [f"  {code:40} {census.DORMANT_UNREACHABLE[code]}"
                for code in sorted(corpus.stale)])
