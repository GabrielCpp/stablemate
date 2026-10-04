"""The book check reports every command, endpoint and screen no flow walks."""
from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from ostler.qa.plan_source import Gap
from workhorse_workflows.okf_book.shared.blockers import Phase, Side
from workhorse_workflows.okf_book.shared.page_check import (
    PageProblem,
    book_problems,
    gap_problems,
    off_journey_nodes,
    tool_blockers,
)

FLOW = Path("docs/features/tally/flows/track-a-trip.md")
COMMANDS = Path("docs/features/tally/tally.md")
UNINVOKABLE_FIX = (
    "When the app itself runs it, delete the page and every page under it, move each other link they hold to "
    + "the page of what calls it so no page they reached is left unlinked, point each link to them at that page, "
    + "and state there what running it changes, with claims that prove it. Do not scaffold it again. When it is "
    + "no one program, give the page the `type:` of what it documents and keep its links. When a user runs it, "
    + "`binary:` names the program, and the operator opts that tool in."
)


def _drop_lines(path: Path, *needles: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if not any(needle in line for needle in needles)]
    _ = path.write_text("".join(kept), encoding="utf-8")


def test_a_book_whose_flow_walks_every_command_has_none_off_journey(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")

    assert off_journey_nodes(repo, "tally") == ()


def test_a_command_no_step_links_is_off_journey(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    _drop_lines(repo / FLOW, "tally export", "CSV.")

    assert off_journey_nodes(repo, "tally") == (f"{COMMANDS.as_posix()}#export",)
    assert any(f"{COMMANDS.as_posix()}#export is on no flow." in problem for problem in book_problems(repo, "tally"))


def test_a_book_with_no_flow_has_every_command_off_journey(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    (repo / FLOW).unlink()

    assert off_journey_nodes(repo, "tally") == tuple(
        f"{COMMANDS.as_posix()}#{command}" for command in ("init", "add", "import", "report", "export")
    )


def test_a_prose_link_from_a_flow_does_not_put_a_command_on_it(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    flow = repo / FLOW
    text = flow.read_text(encoding="utf-8")
    walk, _, prose = text.partition("\n\nThe journey")
    kept = [line for line in walk.splitlines() if "tally report" not in line and "downstream" not in line]
    _ = flow.write_text("\n".join(kept) + "\n\nThe journey" + prose + "\nSee [report](../tally.md#report).\n", encoding="utf-8")

    assert off_journey_nodes(repo, "tally") == (f"{COMMANDS.as_posix()}#report",)


def test_a_claim_no_run_observes_is_the_books_to_restate(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    page = repo / COMMANDS
    text = page.read_text(encoding="utf-8")
    totalled = '- verify: json_path(path="$.total_cents", equals="7450")\n'
    _ = page.write_text(text.replace(totalled, totalled + '- verify: emitted(event="the ledger was read", count=1)\n', 1), encoding="utf-8")

    problems = [problem for problem in book_problems(repo, "tally") if "needs-out-of-band-observation" in problem]

    assert len(problems) == 1
    assert "State what a caller of the surface sees instead" in problems[0]


def test_a_binary_the_repo_opts_into_no_qa_tool_is_the_operators_and_no_problem_of_the_page(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    blocked_while_opted_in = tool_blockers(repo, "tally")
    _drop_lines(repo / "agents.yml", "- python3")

    blockers = tool_blockers(repo, "tally")

    assert blocked_while_opted_in == ()
    assert [problem for problem in book_problems(repo, "tally") if "no run can invoke" in problem] == []
    assert [(blocker.subject, blocker.phase, blocker.side, blocker.pages) for blocker in blockers] == [
        ("tally: QA tool python3", Phase.WRITE, Side.ENVIRONMENT, (COMMANDS.as_posix(),))
    ]
    assert "list `python3` under `qa: tools:` in agents.yml" in blockers[0].reason


def test_a_cli_page_that_names_no_binary_cannot_be_invoked(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    _drop_lines(repo / COMMANDS, "- binary:")

    assert [problem for problem in book_problems(repo, "tally") if "no run can invoke" in problem] == [
        f"{COMMANDS.as_posix()}: no run can invoke it, because it names no `binary:`. " + UNINVOKABLE_FIX
    ]


def test_a_book_no_claim_of_which_declares_a_check_is_a_problem_on_its_entries_page(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    checked = book_problems(repo, "tally")
    book = repo / "docs/features/tally"
    shutil.rmtree(book)
    book.mkdir()
    _ = (book / "entries.md").write_text("---\ntype: entries\ntitle: tally\n---\n# tally\n\n- [ledger](ledger.md)\n", encoding="utf-8")
    _ = (book / "ledger.md").write_text("---\ntype: concept\ntitle: ledger\n---\n# ledger\n\nThe ledger keeps every expense.\n", encoding="utf-8")

    unchecked = [problem for problem in book_problems(repo, "tally") if "declares a check" in problem]

    assert not [problem for problem in checked if "declares a check" in problem]
    assert unchecked == [
        "docs/features/tally/entries.md: no claim of this book declares a check, so a run has nothing to exercise. Give the claims a "
        + "user can observe a `- verify:` bullet that checks what they see, starting with the steps of each flow."
    ]


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
        ),
        PageProblem(page, f"okf:{page}#export:does:1 does not compile: unparsed-check: no check", node=f"{page}#export"),
    ]


def test_a_gap_another_node_owns_is_one_problem_on_the_owner_page_and_none_on_the_claim_pages() -> None:
    page = COMMANDS.as_posix()
    owner = "docs/features/tally/gui/screens/editor.md"
    gaps = [
        Gap(f"okf:{page}#add:does:1", "unreachable-screen", "nothing leads here.", owner),
        Gap(f"okf:{page}#export:does:1", "unreachable-screen", "nothing leads here.", owner),
    ]

    assert gap_problems(gaps) == [
        PageProblem(
            owner,
            f"{owner}: unreachable-screen: nothing leads here. It stops 2 claims from compiling, such as okf:{page}#add:does:1",
            node=owner,
        )
    ]
