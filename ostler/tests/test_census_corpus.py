"""The census verdict, taken where it is sound: over every book of the corpus at once.

`take_census` observes one `doctor` run. The registry it feeds asks whether a rule is
enforced *anywhere*, and "anywhere" is a quantifier over runs — so a verdict read off a
single book names as unenforced every checker some other book or profile exercises. That
is not hypothetical: it is how twenty-nine planning-graph codes came to carry written
excuses, all of which this file's first green run deleted.

So the corpus is the unit. Every book in it now runs the `full` profile — the one that
enters every checker — and a code still unentered after all six runs is one nothing in
this repo enforces. The corpus carried an `exploration` book until globex gained a story
layer; it no longer needs one, because `exploration` runs a strict subset (`doctor.py`
returns early at its one profile gate) and so can enter no checker `full` does not. The
early-return branch itself is observed by `test_model_trace.py`, `test_ui_known_defect.py`
and `test_census.py`, which is where a claim about one code path belongs.
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


def test_the_corpus_enters_every_checker_a_profile_can_gate(corpus: census.Census) -> None:
    """The precondition of every other assertion here, asserted rather than assumed.

    Half of `doctor` is gated on the `full` profile. A corpus that drifted to books which
    all stop at the profile gate would still pass the two gates below — with everything
    behind that gate unentered — and nothing would say so.
    """
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
    """The other direction: a family wired back up must not leave its excuse to pre-waive the next.

    This is the assertion that shrank the registry from thirty-five entries to thirteen. An
    excuse nobody deletes is a stored fact with no observation behind it — false at an
    unknown time, and silently true-looking until something runs it.
    """
    assert not corpus.stale, "\n".join(
        [""] + [f"  {code:40} {census.DORMANT_UNREACHABLE[code]}"
                for code in sorted(corpus.stale)])
