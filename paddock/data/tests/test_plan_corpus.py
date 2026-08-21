"""Every frozen `qa_plan.py` in the corpus must pass the lint that ships today.

`ostler.qa.lint` is an allowlist, and an allowlist tightens: a module leaves
`ALLOWED_IMPORT_MODULES`, a verb joins the rejected set, and a plan that was legal when
it was frozen stops being legal without anyone touching the fixture. What that costs is
not a test failure — it is a *round*. The plan refuses at trial time, the story arrives
as `inconclusive`, and the scoreboard reports a QA lane that detected nothing when what
actually happened is that the benchmark's own input went stale.

This is the cheap half of that guard: a static pass over the tracked tree, no
materialization, no config, so it runs in the same second as the rest of the suite and
fails on the commit that tightened the rule rather than on the next scored round.
`test_tally_cli_app.py::test_the_frozen_plan_lints_and_validates_on_a_trial` is the
expensive half — it lints *and validates* on a materialized trial, which is the only
place `covers=` ids can be bound against a real packet. Neither replaces the other: this
one covers every app, that one covers everything lint alone cannot see.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler.qa.lint import lint_source

DATA = Path(__file__).parents[1]
PLANS = sorted((DATA / "apps").glob("*/docs/specs/*/qa_plan.py"))


def _plan_id(plan: Path) -> str:
    return f"{plan.parents[3].name}/{plan.parent.name}"


def test_the_corpus_has_plans_to_lint() -> None:
    """A glob that matches nothing passes every parametrized test under it, silently."""
    assert PLANS, f"no frozen qa_plan.py found under {DATA / 'apps'}"


@pytest.mark.parametrize("plan", PLANS, ids=_plan_id)
def test_a_frozen_plan_passes_the_lint_that_ships_today(plan: Path) -> None:
    problems = lint_source(plan.read_text(encoding="utf-8"), filename=str(plan))
    assert not problems, "\n".join(problems)
