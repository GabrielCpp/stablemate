"""The book check reports every command, endpoint and screen no flow walks."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_book.shared.page_check import book_problems, compile_services, obligation_page, off_journey_nodes

FLOW = Path("docs/features/tally/flows/track-a-trip.md")
COMMANDS = Path("docs/features/tally/tally.md")


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
