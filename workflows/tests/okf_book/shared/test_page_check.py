"""The book check reports every command, endpoint and screen no flow walks."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ostler.qa.plan_source import Gap
from workhorse_workflows.okf_book.shared.page_check import (
    PageProblem,
    book_problems,
    compile_services,
    gap_problems,
    obligation_page,
    off_journey_nodes,
)

FLOW = Path("docs/features/tally/flows/track-a-trip.md")
COMMANDS = Path("docs/features/tally/tally.md")
UNINVOKABLE_FIX = (
    "When the app itself runs it, delete the page and every page under it, point each link to them at the page "
    + "of what calls it, and state there what running it changes, with claims that prove it. Do not scaffold it "
    + "again. When a user runs it, `binary:` names the program, and the operator opts that tool in."
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


def test_a_compile_states_only_the_named_books_obligations(app: Callable[[str], Path]) -> None:
    repo = app("globex")

    compiled = compile_services(repo, ("api-service",))

    assert compiled.obligations
    assert {obligation_page(obligation).split("/")[2] for obligation in compiled.obligations} == {"api-service"}


def test_a_claim_no_run_observes_is_the_books_to_restate(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    page = repo / COMMANDS
    text = page.read_text(encoding="utf-8")
    totalled = '- verify: json_path(path="$.total_cents", equals="7450")\n'
    _ = page.write_text(text.replace(totalled, totalled + '- verify: emitted(event="the ledger was read", count=1)\n', 1), encoding="utf-8")

    problems = [problem for problem in book_problems(repo, "tally") if "needs-out-of-band-observation" in problem]

    assert len(problems) == 1
    assert "State what a caller of the surface sees instead" in problems[0]


def test_a_cli_page_whose_binary_the_repo_opts_into_no_qa_tool_cannot_be_invoked(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    opted_in = [problem for problem in book_problems(repo, "tally") if "no run can invoke" in problem]
    _drop_lines(repo / "agents.yml", "- python3")

    assert opted_in == []
    assert [problem for problem in book_problems(repo, "tally") if "no run can invoke" in problem] == [
        f"{COMMANDS.as_posix()}: no run can invoke `python3`, because this repository opts no QA tool of that name in. "
        + UNINVOKABLE_FIX
    ]


def test_a_cli_page_that_names_no_binary_cannot_be_invoked(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    _drop_lines(repo / COMMANDS, "- binary:")

    assert [problem for problem in book_problems(repo, "tally") if "no run can invoke" in problem] == [
        f"{COMMANDS.as_posix()}: no run can invoke it, because it names no `binary:`. " + UNINVOKABLE_FIX
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
