"""The book check reports every command, endpoint and screen no flow walks."""
from __future__ import annotations

from pathlib import Path

from ostler.qa.plan_source import Gap
from workhorse_workflows.okf_book.shared.page_check import (
    PageProblem,
    gap_problems,
)
COMMANDS = Path("docs/services/tally/tally.md")

def test_gaps_are_grouped_per_node_so_each_problem_names_the_claims_of_one_node() -> None:
    page = COMMANDS.as_posix()
    gaps = [
        Gap(f"okf:{page}#add:does:1", "unparsed-check", "no check"),
        Gap(f"okf:{page}#add:does:2", "unparsed-check", "no check"),
        Gap(f"okf:{page}#export:does:1", "unparsed-check", "no check"),
    ]

    assert gap_problems(gaps) == [
        PageProblem(
            page,
            f"each of 2 claims on {page}#add does not compile: unparsed-check: no check "
            + f"The claims: okf:{page}#add:does:1, okf:{page}#add:does:2",
            node=f"{page}#add",
            code="unparsed-check",
        ),
        PageProblem(page, f"okf:{page}#export:does:1 does not compile: unparsed-check: no check", node=f"{page}#export", code="unparsed-check"),
    ]


def test_a_gap_another_node_owns_is_one_problem_on_the_owner_page_and_none_on_the_claim_pages() -> None:
    page = COMMANDS.as_posix()
    owner = "docs/services/tally/gui/screens/editor.md"
    gaps = [
        Gap(f"okf:{page}#add:does:1", "unreachable-screen", "nothing leads here.", owner),
        Gap(f"okf:{page}#export:does:1", "unreachable-screen", "nothing leads here.", owner),
    ]

    assert gap_problems(gaps) == [
        PageProblem(
            owner,
            f"{owner}: unreachable-screen: nothing leads here. It stops 2 claims from compiling, such as okf:{page}#add:does:1",
            node=owner,
            code="unreachable-screen",
        )
    ]
