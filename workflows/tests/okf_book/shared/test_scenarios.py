"""A failed scenario's report lands on the book pages whose obligations it covers."""
from __future__ import annotations

from ostler.qa.attribution import Cause, Signature
from ostler.qa.verdict import Verdict

from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, Scenario, ScenarioOutcome, Selection, select_scenarios

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


def test_a_check_made_for_one_claim_is_reported_on_that_claims_page_alone() -> None:
    claim = "okf:docs/features/tally/tally.md#add:does:2"
    failed = ScenarioOutcome(
        status="failed",
        failed_checks=(FailedCheck(label="POST /add answers [201]", expected="[201]", actual="403", covers=(claim,)),),
    )
    summary = RunSummary(status="failed", scenarios={"tally-add": failed})

    by_page = summary.failures_by_page((ADD_SCENARIO,))

    assert by_page == {"docs/features/tally/tally.md": (PageProblem(
        "docs/features/tally/tally.md",
        f"the run of scenario tally-add failed at {claim}: POST /add answers [201]: expected [201], observed 403",
        node="docs/features/tally/tally.md#add"),)}


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


def test_a_scenario_stopped_before_its_first_mark_names_no_obligation_of_the_scenario_above() -> None:
    plan = "\n".join(
        (
            "def tally_add(qa):",
            "    # okf:docs/features/tally/tally.md#add:does:1",
            "    qa.http.post('/entries', expect_status=400)",
            "",
            "def tally_list(qa):",
            "    token = qa.fixture('signed-in-user')",
            "    # okf:docs/features/tally/tally.md#list:does:1",
            "    qa.http.get('/entries')",
        )
    )
    message = "\n".join(
        (
            "Traceback (most recent call last):",
            '  File "/runs/okf-book-1/spec/tally/qa_plan.py", line 6, in tally_list',
            "    token = qa.fixture('signed-in-user')",
            "FixtureError: step 1 exited 22",
        )
    )
    summary = RunSummary(status="failed", scenarios={"tally-list": ScenarioOutcome(status="failed", message=message)})

    by_page = summary.failures_by_page((LIST_SCENARIO,), plan)

    assert by_page == {
        "docs/features/tally/tally.md": (
            PageProblem("docs/features/tally/tally.md", "the run of scenario tally-list failed: FixtureError: step 1 exited 22"),
        )
    }


def test_a_journey_stopped_at_a_step_is_reported_on_the_page_of_the_node_that_step_performs() -> None:
    journey = Scenario(id="budget-journey", covers=("okf:docs/features/tally/flows/budget.md:end:1",))
    plan = "\n".join(
        (
            "def budget_journey(qa):",
            "    # okf:docs/features/tally/api.md#list-entries",
            "    observed_1 = qa.http.get('/entries')",
            "    # okf:docs/features/tally/flows/budget.md:end:1",
            "    qa.verify('http_status', observed_1, code=200)",
        )
    )
    message = "\n".join(
        (
            "Traceback (most recent call last):",
            '  File "/runs/okf-book-1/spec/tally/qa_plan.py", line 3, in budget_journey',
            "    observed_1 = qa.http.get('/entries')",
            "HttpError: GET http://localhost/entries returned 400: month is required",
        )
    )
    summary = RunSummary(status="failed", scenarios={"budget-journey": ScenarioOutcome(status="failed", message=message)})

    by_page = summary.failures_by_page((journey,), plan)

    text = (
        "the run of scenario budget-journey failed at okf:docs/features/tally/api.md#list-entries: "
        + "HttpError: GET http://localhost/entries returned 400: month is required"
    )
    assert by_page == {
        "docs/features/tally/api.md": (PageProblem("docs/features/tally/api.md", text, node="docs/features/tally/api.md#list-entries"),),
        "docs/features/tally/flows/budget.md": (PageProblem("docs/features/tally/flows/budget.md", text),),
    }


SIGNED_IN = "docs/features/tally/fixtures/signed-in.md"


def test_checks_a_precondition_arranged_wrong_land_once_on_its_page_and_not_on_their_claims() -> None:
    claim = "okf:docs/features/tally/tally.md#add:does:2"
    refused = FailedCheck(label="POST /add answers [201]", expected="[201]", actual="403", covers=(claim,),
                          cause=Cause.ARRANGEMENT, precondition=SIGNED_IN, status="403")
    signature = Signature(Cause.ARRANGEMENT, SIGNED_IN, "403", "", 7, "POST /add answers [201]: expected [201], observed 403")
    summary = RunSummary(status="failed", scenarios={"tally-add": ScenarioOutcome(status="failed", failed_checks=(refused,))},
                         signatures=(signature,))

    by_page = summary.failures_by_page((ADD_SCENARIO,))

    assert by_page == {SIGNED_IN: (PageProblem(
        SIGNED_IN,
        f"7 checks failed on what this page arranges (arrangement: {SIGNED_IN} answered 403); "
        + "for example POST /add answers [201]: expected [201], observed 403",
        requests=("docs/features/tally/tally.md",)),)}


def test_a_scenario_whose_every_check_another_party_must_fix_reaches_no_page() -> None:
    crashed = FailedCheck(label="GET /entries answers [200]", expected="[200]", actual="500", cause=Cause.APP, status="500")
    outcome = ScenarioOutcome(status="failed", message="exit status 1", failed_checks=(crashed,))
    summary = RunSummary(status="failed", scenarios={"tally-list": outcome})

    assert summary.failures_by_page((LIST_SCENARIO,)) == {}


def test_a_check_from_a_run_that_attributed_nothing_is_the_books() -> None:
    summary = RunSummary.model_validate({
        "status": "failed",
        "scenarios": {"tally-list": {"status": "failed", "failed_checks": [{"label": "lists", "expected": "1", "actual": "0"}]}},
    })

    assert summary.scenarios["tally-list"].failed_checks[0].cause is Cause.BOOK
    assert summary.signatures == ()


def test_a_run_summary_reads_back_its_signatures() -> None:
    written = {"cause": "environment", "precondition": "", "status": "could not connect", "shape": "GET /entries/…",
               "count": 3, "sample": "lists"}

    summary = RunSummary.model_validate({"status": "failed", "signatures": [written]})

    assert summary.signatures == (Signature(Cause.ENVIRONMENT, "", "could not connect", "GET /entries/…", 3, "lists"),)
    assert RunSummary.model_validate_json(summary.model_dump_json()) == summary


def test_a_run_summary_reads_back_each_claims_verdict_and_what_a_stop_left_unreached() -> None:
    claims = ("okf:docs/features/tally/tally.md#list:does:1", "okf:docs/features/tally/tally.md#list:does:2")
    summary = RunSummary.model_validate({
        "status": "failed",
        "scenarios": {"tally-list": {"status": "failed", "unreached": [claims[1]]}},
        "verdicts": {claims[0]: "pass", claims[1]: "unreached"},
    })

    assert summary.scenarios["tally-list"].unreached == (claims[1],)
    assert summary.verdicts == {claims[0]: Verdict.PASS, claims[1]: Verdict.UNREACHED}
    assert RunSummary.model_validate_json(summary.model_dump_json()) == summary


SEED_SCENARIO = Scenario(id="tally-seeded", covers=("okf:docs/features/tally/reports.md#monthly:does:1",))
SEEDED = {"seeded-ledger": ("okf:docs/features/tally/reports.md#monthly:does:1", "okf:docs/features/tally/tally.md#list:does:1")}


def test_a_page_selects_every_scenario_that_covers_it() -> None:
    selected = select_scenarios((ADD_SCENARIO, LIST_SCENARIO, SEED_SCENARIO), SEEDED, ("docs/features/tally/tally.md",))

    assert selected == Selection(scenarios=("tally-add", "tally-list"))


def test_a_fixture_page_selects_the_first_scenario_that_arranges_its_fixture() -> None:
    selected = select_scenarios((ADD_SCENARIO, LIST_SCENARIO, SEED_SCENARIO), SEEDED, ("docs/features/tally/fixtures/seeded-ledger.md",))

    assert selected == Selection(scenarios=("tally-list",))


def test_a_target_no_scenario_runs_is_named_back() -> None:
    selected = select_scenarios((ADD_SCENARIO,), SEEDED, ("docs/features/tally/flows/budget.md", "docs/features/tally/missing.md"))

    assert selected == Selection(scenarios=("tally-add",), unmatched=("docs/features/tally/missing.md",))


def test_a_signature_names_the_page_that_arranged_its_checks_then_the_pages_they_cover() -> None:
    refused = FailedCheck(label="adds", cause=Cause.ARRANGEMENT, precondition="docs/fixtures/admin.md", status="400",
                          covers=("okf:docs/features/tally/tally.md#list:does:1", "okf:docs/features/tally/add.md:contract"))
    other = FailedCheck(label="lists", cause=Cause.APP, status="500", covers=("okf:docs/features/tally/other.md:contract",))
    summary = RunSummary(status="failed", scenarios={"tally-add": ScenarioOutcome(status="failed", failed_checks=(refused, other))})
    signature = Signature(Cause.ARRANGEMENT, "docs/fixtures/admin.md", "400", "", 1, "adds")

    assert summary.signature_pages(signature) == (
        "docs/fixtures/admin.md", "docs/features/tally/add.md", "docs/features/tally/tally.md")
