"""A failed scenario's report lands on the book pages whose obligations it covers."""
from __future__ import annotations

from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, Scenario, ScenarioOutcome

ADD_SCENARIO = Scenario(
    id="tally-add",
    covers=(
        "okf:docs/features/tally/tally.md#add:does:1",
        "okf:docs/features/tally/tally.md#add:does:2",
        "okf:docs/features/tally/flows/budget.md:end:1",
    ),
)
LIST_SCENARIO = Scenario(id="tally-list", covers=("okf:docs/features/tally/tally.md#list:does:1",))


def test_a_scenario_names_each_page_its_obligations_sit_on_once() -> None:
    assert ADD_SCENARIO.pages == ("docs/features/tally/tally.md", "docs/features/tally/flows/budget.md")


def test_each_failed_scenario_reports_on_every_page_it_covers_and_a_passing_one_on_none() -> None:
    failed = ScenarioOutcome(
        status="failed",
        message="exit status 1\nthe ledger refused the entry",
        failed_checks=(FailedCheck(label="adds an expense", expected="0", actual="1"),),
    )
    summary = RunSummary(status="failed", scenarios={"tally-add": failed, "tally-list": ScenarioOutcome(status="passed")})

    by_page = summary.failures_by_page((ADD_SCENARIO, LIST_SCENARIO))

    expected = (
        "the run of scenario tally-add failed: adds an expense: expected 0, observed 1",
        "the run of scenario tally-add failed: the ledger refused the entry",
    )
    assert {page: tuple(problem.text for problem in problems) for page, problems in by_page.items()} == {
        "docs/features/tally/flows/budget.md": expected,
        "docs/features/tally/tally.md": expected,
    }
    assert all(problem.page == page and not problem.node for page, problems in by_page.items() for problem in problems)


def test_a_scenario_stopped_inside_the_plan_is_reported_at_the_obligation_it_stopped_in() -> None:
    plan = "\n".join(
        (
            "def tally_add(qa):",
            "    # okf:docs/features/tally/tally.md#add:does:1",
            "    qa.http.post('/entries', expect_status=400)",
            "",
            "    # okf:docs/features/tally/tally.md#add:does:2",
            "    # records the entry.",
            "    observed = qa.http.post('/entries', json_body={'amount': 3})",
            "    qa.verify('http_status', observed, code=201)",
        )
    )
    message = "\n".join(
        (
            "Traceback (most recent call last):",
            '  File "/runs/okf-book-1/spec/tally/qa_plan.py", line 7, in tally_add',
            "    observed = qa.http.post('/entries', json_body={'amount': 3})",
            '  File "/harness/ostler_qa.py", line 480, in request',
            "HttpError: POST http://localhost/entries returned 404: ledger not found",
        )
    )
    summary = RunSummary(status="failed", scenarios={"tally-list": ScenarioOutcome(status="failed", message=message)})

    by_page = summary.failures_by_page((LIST_SCENARIO,), plan)

    assert by_page == {
        "docs/features/tally/tally.md": (
            PageProblem(
                "docs/features/tally/tally.md",
                "the run of scenario tally-list failed at okf:docs/features/tally/tally.md#add:does:2: "
                + "HttpError: POST http://localhost/entries returned 404: ledger not found",
                node="docs/features/tally/tally.md#add",
            ),
        )
    }
