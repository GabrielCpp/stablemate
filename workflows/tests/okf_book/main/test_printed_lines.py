"""What a writer's command prints into its turn."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.check_pages import USAGE, checked
from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    MAX_PRINTED_LINES,
    PRINTED_LINE_CHARS,
    WriterCommandState,
    printed_lines,
    write_command_state,
)


def test_a_command_prints_its_first_lines_and_counts_the_rest() -> None:
    lines = [f"problem {n}" for n in range(MAX_PRINTED_LINES + 5)]

    printed = printed_lines(lines)

    assert printed[:-1] == tuple(lines[:MAX_PRINTED_LINES])
    assert printed[-1].startswith("… and 5 more")
    assert printed_lines(lines[:3]) == tuple(lines[:3])


def test_hidden_lines_that_only_continue_the_last_item_hide_no_other_item() -> None:
    lines = ["scenario a: failed", *(f"    log line {n}" for n in range(MAX_PRINTED_LINES + 5))]

    printed = printed_lines(lines)

    assert printed[-1] == "… and 6 more indented lines of the item above, and no other item"


def test_hidden_lines_count_the_items_they_start() -> None:
    lines = [*(f"scenario {n}: failed" for n in range(MAX_PRINTED_LINES)), "  check x failed", "scenario y: failed", "  check y failed"]

    printed = printed_lines(lines)

    assert printed[-1] == "… and 3 more lines, 1 of them starting another item: fix these, then run it again"


def test_a_command_prints_each_line_whole_within_the_characters_of_one_run() -> None:
    lines = ["x" * (PRINTED_LINE_CHARS * 3)] * MAX_PRINTED_LINES

    printed = printed_lines(lines)

    assert printed[:-1] == tuple(lines[: MAX_PRINTED_LINES // 3])
    assert printed[-1].startswith(f"… and {MAX_PRINTED_LINES - MAX_PRINTED_LINES // 3} more")
    assert sum(len(line) for line in printed[:-1]) <= MAX_PRINTED_LINES * PRINTED_LINE_CHARS


def test_a_command_clips_a_first_line_longer_than_one_run() -> None:
    printed = printed_lines(["x" * (MAX_PRINTED_LINES * PRINTED_LINE_CHARS * 2), "next"])

    assert len(printed[0]) == MAX_PRINTED_LINES * PRINTED_LINE_CHARS
    assert printed[0].endswith("…")
    assert printed[1].startswith("… and 1 more")


def test_a_check_refuses_an_argument_that_names_no_page(tmp_path: Path) -> None:
    path = write_command_state(tmp_path / "run", WriterCommandState(root=tmp_path, service="ledger"))

    output = checked([str(path), "--json"])

    assert output.code == 2
    assert output.lines[0].startswith("--json is no page")
    assert output.lines[-1] == USAGE
