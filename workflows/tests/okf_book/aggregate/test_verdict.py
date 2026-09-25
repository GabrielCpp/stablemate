"""The judge accounts for each numbered claim, and the code decides the pass from what it accounts and what it cleared before."""
from __future__ import annotations

from pathlib import Path

import pytest

from workhorse_workflows.okf_book.aggregate.verdict import (
    GRAMMAR_GAPS_NAME,
    ClaimFinding,
    GrammarGap,
    NodeProblem,
    Verdict,
    claim_texts,
    cleared_after,
    grammar_gaps,
    refuse_unread_nodes,
    numbered_contracts,
    record_grammar_gaps,
    still_cleared,
    verdict_problems,
)
from workhorse_workflows.okf_book.shared.attempts import ClearedNode
from workhorse_workflows.okf_book.shared.contracts import Claim, Contract

CONTRACTS = (
    Contract(file="tally/add.py", purpose="Adds a row.", promises=(Claim(text="It appends a row.", symbol="add"),),
             refusals=(Claim(text="It refuses a non-numeric amount.", symbol="add"),)),
    Contract(file="tally/report.py", purpose="Prints totals.", promises=(Claim(text="It prints one total per category."),)),
)
DIGESTS = {"page.md": "p1", "page.md#add": "a1", "page.md#report": "r1"}


def test_claims_are_numbered_across_contracts_promises_before_refusals() -> None:
    numbered = numbered_contracts(CONTRACTS)

    assert [[(c.id, c.text) for c in contract.claims] for contract in numbered] == [
        [(1, "It appends a row."), (2, "It refuses a non-numeric amount.")],
        [(3, "It prints one total per category.")],
    ]


def test_a_verdict_that_states_every_claim_with_no_problem_passes() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(claims=tuple(ClaimFinding(claim=n, node=f"page.md#n{n}") for n in (1, 2, 3)))

    assert verdict_problems(verdict, claims, ()) == ()


def test_each_claim_with_no_node_is_named_with_its_code() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(claims=(ClaimFinding(claim=1, node="page.md#add"), ClaimFinding(claim=2)))

    problems = verdict_problems(verdict, claims, ())

    assert len(problems) == 2
    assert "Claim 2, It refuses a non-numeric amount. (`tally/add.py::add`), is stated on no page." in problems[0]
    assert "Claim 3, It prints one total per category. (`tally/report.py`), is stated on no page." in problems[1]


def test_a_finding_s_problem_and_the_uncovered_problems_are_charged_after_the_unstated_claims() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add", problem="its check passes on a violation."),
                ClaimFinding(claim=2, node="page.md#add"), ClaimFinding(claim=3, node="page.md#report")),
        problems=(NodeProblem(node="page.md#report", problem="the example contradicts the exit code."),),
    )

    assert verdict_problems(verdict, claims, ()) == (
        "page.md#add: its check passes on a violation.",
        "page.md#report: the example contradicts the exit code.",
    )


def test_a_cleared_node_stands_only_while_its_digest_is_unchanged() -> None:
    cleared = (ClearedNode(node="page.md#add", digest="a1"), ClearedNode(node="page.md#report", digest="r0"))

    assert [entry.node for entry in still_cleared(cleared, DIGESTS)] == ["page.md#add"]


def test_a_problem_on_a_node_still_cleared_is_dropped_and_the_claims_it_states_count() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    cleared = (ClearedNode(node="page.md#add", digest="a1", claims=(claims[0], claims[1])),)
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add", problem="its check passes on a violation."),
                ClaimFinding(claim=3, node="page.md#report")),
        problems=(NodeProblem(node="page.md#add", problem="it contradicts the report."),),
    )

    assert verdict_problems(verdict, claims, still_cleared(cleared, DIGESTS)) == ()


def test_a_problem_on_a_cleared_node_whose_text_changed_is_charged() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    cleared = (ClearedNode(node="page.md#add", digest="a0", claims=(claims[1],)),)
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add"), ClaimFinding(claim=3, node="page.md#report")),
        problems=(NodeProblem(node="page.md#add", problem="it contradicts the report."),),
    )

    problems = verdict_problems(verdict, claims, still_cleared(cleared, DIGESTS))

    assert len(problems) == 2
    assert "Claim 2," in problems[0]
    assert problems[1] == "page.md#add: it contradicts the report."


def test_every_judged_node_nothing_was_raised_against_is_cleared_with_the_claims_it_states() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add"), ClaimFinding(claim=2, node="page.md#add"),
                ClaimFinding(claim=3, node="page.md#report", problem="its check passes on a violation.")),
        problems=(NodeProblem(node="page.md", problem="the intro names no command."),),
    )

    assert cleared_after(verdict, claims, DIGESTS, ()) == (
        ClearedNode(node="page.md#add", digest="a1", claims=tuple(sorted(claims[:2]))),
    )


def test_a_node_still_cleared_keeps_its_claims_whatever_this_round_says_of_it() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    cleared = (ClearedNode(node="page.md#report", digest="r1", claims=(claims[2],)),)
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add"), ClaimFinding(claim=2, node="page.md#add"),
                ClaimFinding(claim=3)),
        problems=(NodeProblem(node="page.md#report", problem="it contradicts the add section."),),
    )

    after = {entry.node: entry for entry in cleared_after(verdict, claims, DIGESTS, still_cleared(cleared, DIGESTS))}

    assert set(after) == {"page.md", "page.md#add", "page.md#report"}
    assert after["page.md#report"] == ClearedNode(node="page.md#report", digest="r1", claims=(claims[2],))


def test_a_node_still_cleared_on_a_page_this_round_did_not_judge_stays_cleared() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    unread = ClearedNode(node="other.md#sum", digest="s1", claims=(claims[2],))
    verdict = Verdict(claims=(ClaimFinding(claim=1, node="page.md#add"), ClaimFinding(claim=2, node="page.md#add"), ClaimFinding(claim=3)))

    assert verdict_problems(verdict, claims, (unread,)) == ()
    assert unread in cleared_after(verdict, claims, DIGESTS, (unread,))


def test_a_problem_carries_the_check_the_judge_expected_in_its_canonical_spelling() -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add", problem="its check reads stdout.",
                             expected='json_path(file="tally.json", path="rows[0]", equals=1)'),
                ClaimFinding(claim=2, node="page.md#add"), ClaimFinding(claim=3, node="page.md#report")),
        problems=(NodeProblem(node="page.md#report", problem="it checks no exit code.", expected="exit_status(1)"),),
    )

    assert verdict_problems(verdict, claims, ()) == (
        'page.md#add: its check reads stdout. The check that reads it: '
        '`verify: json_path(path="rows[0]", equals=1, file="tally.json")`.',
        "page.md#report: it checks no exit code. The check that reads it: `verify: exit_status(code=1)`.",
    )
    assert grammar_gaps(verdict) == ()


def test_a_check_the_grammar_refuses_is_left_out_of_the_problem_and_recorded_as_a_gap(tmp_path: Path) -> None:
    claims = claim_texts(numbered_contracts(CONTRACTS))
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add", problem="no check reads the sort order.",
                             expected='sorted(subject="rows")'),
                ClaimFinding(claim=2, node="page.md#add"), ClaimFinding(claim=3, node="page.md#report")),
    )

    assert verdict_problems(verdict, claims, ()) == ("page.md#add: no check reads the sort order.",)
    [gap] = grammar_gaps(verdict)
    assert (gap.node, gap.expected) == ("page.md#add", 'sorted(subject="rows")')
    assert "sorted" in gap.refusal

    record_grammar_gaps(tmp_path, (gap,))
    record_grammar_gaps(tmp_path, (gap,))
    lines = (tmp_path / GRAMMAR_GAPS_NAME).read_text(encoding="utf-8").splitlines()
    assert [GrammarGap.model_validate_json(line) for line in lines] == [gap]


def test_no_gap_is_recorded_when_the_judge_expected_no_check(tmp_path: Path) -> None:
    record_grammar_gaps(tmp_path, grammar_gaps(Verdict(problems=(NodeProblem(node="page.md", problem="a typo."),))))

    assert not (tmp_path / GRAMMAR_GAPS_NAME).exists()


def test_a_verdict_naming_only_nodes_on_pages_the_judge_read_is_accepted() -> None:
    verdict = Verdict(
        claims=(ClaimFinding(claim=1, node="page.md#add"), ClaimFinding(claim=2)),
        problems=(NodeProblem(node="page.md", problem="the page states no exit code."),),
    )

    refuse_unread_nodes(verdict, ("page.md",))


def test_a_placeholder_node_sends_the_verdict_back_naming_the_pages_it_may_name() -> None:
    verdict = Verdict(problems=(NodeProblem(node="...", problem="...", expected="..."),))

    with pytest.raises(ValueError, match="no page you read: '...'") as refused:
        refuse_unread_nodes(verdict, ("page.md", "other.md"))

    assert "one of other.md, page.md" in str(refused.value)


def test_a_claim_stated_on_a_page_the_judge_did_not_read_sends_the_verdict_back() -> None:
    verdict = Verdict(claims=(ClaimFinding(claim=1, node="elsewhere.md#add"),))

    with pytest.raises(ValueError, match="'elsewhere.md#add'"):
        refuse_unread_nodes(verdict, ("page.md",))
