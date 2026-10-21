"""Which side a failed scenario sits on, from the causes of its failed checks."""
from __future__ import annotations

import pytest
from ostler.qa.attribution import Cause

from workhorse_workflows.coder.qa.sides import run_sides, scenario_cause
from workhorse_workflows.kit.qa.schemas import QaPlanRun


@pytest.mark.parametrize(
    ("causes", "side"),
    [
        (("app", "environment", "book"), Cause.ENVIRONMENT),
        (("app", "book", "arrangement"), Cause.ARRANGEMENT),
        (("app", "book"), Cause.BOOK),
        (("unattributed", "app"), Cause.APP),
        (("unattributed",), Cause.UNATTRIBUTED),
        (("a cause ostler does not name",), Cause.UNATTRIBUTED),
        ((), Cause.UNATTRIBUTED),
    ],
)
def test_a_scenario_takes_the_side_that_must_be_fixed_first(
    causes: tuple[str, ...], side: Cause
) -> None:
    """The world has to stand before the book is judged, and the book before the product."""
    assert scenario_cause(tuple({"cause": c} for c in causes)) is side


def test_a_run_splits_its_failed_scenarios_by_side() -> None:
    """Book and arrangement share one owner, and a scenario with no checks is unattributed."""
    run = QaPlanRun(
        status="failed",
        ostler={
            "scenarios": {
                "a": {"status": "failed", "failed_checks": [{"cause": "arrangement"}]},
                "b": {"status": "failed", "failed_checks": [{"cause": "book"}]},
                "c": {"status": "failed", "failed_checks": [{"cause": "app"}]},
                "d": {"status": "aborted"},
                "e": {"status": "failed", "failed_checks": [{"cause": "environment"}]},
                "f": {"status": "passed"},
            }
        },
    )

    sides = run_sides(run)

    assert [s.id for s in sides.book] == ["a", "b"]
    assert [s.id for s in sides.product] == ["c"]
    assert [s.id for s in sides.unattributed] == ["d"]
    assert [s.id for s in sides.environment] == ["e"]
