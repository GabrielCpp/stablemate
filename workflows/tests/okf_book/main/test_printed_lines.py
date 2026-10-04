"""What a writer's command prints into its turn."""
from __future__ import annotations

from workhorse_workflows.okf_book.main.nodes.writer_commands import MAX_PRINTED_LINES, PRINTED_LINE_CHARS, printed_lines


def test_a_command_prints_its_first_lines_and_counts_the_rest() -> None:
    lines = [f"problem {n}" for n in range(MAX_PRINTED_LINES + 5)]

    printed = printed_lines(lines)

    assert printed[:-1] == tuple(lines[:MAX_PRINTED_LINES])
    assert printed[-1].startswith("… and 5 more")
    assert printed_lines(lines[:3]) == tuple(lines[:3])


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
