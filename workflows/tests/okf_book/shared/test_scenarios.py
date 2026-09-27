"""A failed scenario's report lands on the book pages whose obligations it covers."""
from __future__ import annotations

from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, Scenario, ScenarioOutcome

ADD = Scenario(
    id="tally-add",
    covers=(
        "okf:docs/features/tally/tally.md#add:does:1",
        "okf:docs/features/tally/tally.md#add:does:2",
        "okf:docs/features/tally/flows/budget.md:end:1",
    ),
)
LIST = Scenario(id="tally-list", covers=("okf:docs/features/tally/tally.md#list:does:1",))


def test_a_scenario_names_each_page_its_obligations_sit_on_once() -> None:
    assert ADD.pages == ("docs/features/tally/tally.md", "docs/features/tally/flows/budget.md")


def test_each_failed_scenario_reports_on_every_page_it_covers_and_a_passing_one_on_none() -> None:
    failed = ScenarioOutcome(
        status="failed",
        message="exit status 1\nthe ledger refused the entry",
        failed_checks=(FailedCheck(label="adds an expense", expected="0", actual="1"),),
    )
    summary = RunSummary(status="failed", scenarios={"tally-add": failed, "tally-list": ScenarioOutcome(status="passed")})

    by_page = summary.failures_by_page((ADD, LIST))

    expected = (
        "the run of scenario tally-add failed: adds an expense: expected 0, observed 1",
        "the run of scenario tally-add failed: the ledger refused the entry",
    )
    assert by_page == {"docs/features/tally/flows/budget.md": expected, "docs/features/tally/tally.md": expected}
