"""The census verdict, taken where it is sound: over every book of the corpus at once.

`take_census` observes one `doctor` run. The registry it feeds asks whether a rule is
enforced *anywhere*, and "anywhere" is a quantifier over runs — so a verdict read off a
single book names as unenforced every checker some other book or profile exercises. That
is not hypothetical: it is how twenty-nine planning-graph codes came to carry written
excuses, all of which this file's first green run deleted.

So the corpus is the unit. It covers both profiles (globex is the tree's only
`exploration` book) and both fixture tiers, and a code still unentered after all six runs
is one nothing in this repo enforces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import census, doctor
from ostler.model import load

APPS = Path(__file__).resolve().parents[2] / "paddock" / "data" / "apps"


@pytest.fixture(scope="module")
def corpus() -> census.Census:
    """One census per app of the corpus, merged.

    Module-scoped because it traces six full `doctor` runs, and because every assertion
    below is about the same one merge — splitting it per test would ask six different
    questions of six different observations and call them one gate.
    """
    books = sorted(app for app in APPS.iterdir() if (app / "docs" / "features").is_dir())
    assert books, f"no corpus books under {APPS} — the gate below would pass vacuously"
    return census.merge(
        census.take_census(lambda graph=load(app): doctor.run(graph, check_schema=True))
        for app in books
    )


def test_the_corpus_covers_more_than_one_profile(corpus: census.Census) -> None:
    """The precondition of every other assertion here, asserted rather than assumed.

    Half of `doctor` is gated on the `full` profile. A corpus that lost its one
    `exploration` book would still pass the two gates below — with the fixture-grammar tier
    unobserved — and nothing would say so.
    """
    assert set(corpus.profile.split("+")) == {"exploration", "full"}, corpus.profile
    assert corpus.runs >= 2


def test_no_checker_is_unentered_by_the_whole_corpus_without_a_recorded_reason(
    corpus: census.Census,
) -> None:
    """The gate: a rule that stops being enforced must be a decision, not a thing that happened."""
    assert not corpus.undeclared, "\n".join(
        [""] + [f"  {code:40} {', '.join(sorted(corpus.sites.get(code, ())))}"
                for code in sorted(corpus.undeclared)])


def test_no_recorded_reason_outlives_the_code_it_excused(corpus: census.Census) -> None:
    """The other direction: a family wired back up must not leave its excuse to pre-waive the next.

    This is the assertion that shrank the registry from thirty-five entries to thirteen. An
    excuse nobody deletes is a stored fact with no observation behind it — false at an
    unknown time, and silently true-looking until something runs it.
    """
    assert not corpus.stale, "\n".join(
        [""] + [f"  {code:40} {census.DORMANT_UNREACHABLE[code]}"
                for code in sorted(corpus.stale)])
