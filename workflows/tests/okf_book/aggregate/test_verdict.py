"""The judge accounts for each numbered claim, and the code decides the pass from what it accounts."""
from __future__ import annotations

from workhorse_workflows.okf_book.aggregate.verdict import ClaimFinding, Verdict, claim_texts, numbered_contracts, verdict_problems
from workhorse_workflows.okf_book.shared.contracts import Claim, Contract

CONTRACTS = (
    Contract(file="tally/add.py", purpose="Adds a row.", promises=(Claim(text="It appends a row.", symbol="add"),),
             refusals=(Claim(text="It refuses a non-numeric amount.", symbol="add"),)),
    Contract(file="tally/report.py", purpose="Prints totals.", promises=(Claim(text="It prints one total per category."),)),
)


def test_claims_are_numbered_across_contracts_promises_before_refusals() -> None:
    numbered = numbered_contracts(CONTRACTS)

    assert [[(c.id, c.text) for c in contract.claims] for contract in numbered] == [
        [(1, "It appends a row."), (2, "It refuses a non-numeric amount.")],
        [(3, "It prints one total per category.")],
    ]


def test_a_verdict_that_states_every_claim_with_no_problem_passes() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(claims=tuple(ClaimFinding(claim=n, node=f"page.md#n{n}") for n in (1, 2, 3)))

    assert verdict_problems(verdict, claims) == ()


def test_each_claim_with_no_node_is_named_with_its_code() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(claims=(ClaimFinding(claim=1, node="page.md#add"), ClaimFinding(claim=2)))

    problems = verdict_problems(verdict, claims)

    assert len(problems) == 2
    assert "Claim 2, It refuses a non-numeric amount. (`tally/add.py::add`), is stated on no page." in problems[0]
    assert "Claim 3, It prints one total per category. (`tally/report.py`), is stated on no page." in problems[1]


def test_a_finding_s_problem_and_the_uncovered_problems_are_charged_after_the_unstated_claims() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add", problem="its check passes on a violation."),
                ClaimFinding(claim=2, node="page.md#add"), ClaimFinding(claim=3, node="page.md#report")),
        problems=("page.md#report: the example contradicts the exit code.",),
    )

    assert verdict_problems(verdict, claims) == (
        "page.md#add: its check passes on a violation.",
        "page.md#report: the example contradicts the exit code.",
    )
