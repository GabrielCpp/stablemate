"""How much one writer turn reads, held against the budget that turn is packed under.

The turn reads the prompt and the format skill, the product's source, the book it finds or writes,
the output of the commands it runs, and the envelope of each step it takes. The prompt, the skill,
the operator's latest answer, the output of every check and ostler run the turn may make and the envelope of every step are fixed
allowances, so the source and the book get what is left. The source is counted twice, since the turn
reads it once and reads it again as it checks its claims against it. A book the writer has not
written yet is counted at twice its source, since the tally book runs 1.8 times its source. The book
is counted twice over, since the turn holds each page once as it writes it and again as it reads it
back.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_AND_SCENARIO_RUN_CAP,
    OSTLER_MAX_PRINTED_LINES,
    OSTLER_RUN_CAP,
    PRINTED_LINE_CHARS,
    MAX_PRINTED_LINES,
)

CHARS_PER_TOKEN = 4
TURN_BUDGET_TOKENS = 180_000
PROMPT_AND_SKILL_ALLOWANCE_TOKENS = 80_000
OPERATOR_ANSWER_ALLOWANCE_TOKENS = 2_000
CHECK_AND_SCENARIO_ALLOWANCE_TOKENS = CHECK_AND_SCENARIO_RUN_CAP * (MAX_PRINTED_LINES + 1) * PRINTED_LINE_CHARS // CHARS_PER_TOKEN
OSTLER_ALLOWANCE_TOKENS = OSTLER_RUN_CAP * (OSTLER_MAX_PRINTED_LINES + 1) * PRINTED_LINE_CHARS // CHARS_PER_TOKEN
WRITER_STEPS = 200
STEP_ENVELOPE_TOKENS = 100
STEP_ALLOWANCE_TOKENS = WRITER_STEPS * STEP_ENVELOPE_TOKENS
SOURCE_AND_BOOK_CEILING_TOKENS = (
    TURN_BUDGET_TOKENS
    - PROMPT_AND_SKILL_ALLOWANCE_TOKENS
    - OPERATOR_ANSWER_ALLOWANCE_TOKENS
    - CHECK_AND_SCENARIO_ALLOWANCE_TOKENS
    - OSTLER_ALLOWANCE_TOKENS
    - STEP_ALLOWANCE_TOKENS
)
SOURCE_READS = 2
BOOK_PER_SOURCE_TOKEN = 2
BOOK_HOLDS = 2
SKIPPED_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules"})


def countable_files(folder: Path) -> Iterator[Path]:
    """Every file under `folder`, outside the tool and dependency folders."""
    if not folder.is_dir():
        return
    for path in folder.rglob("*"):
        if path.is_file() and not SKIPPED_DIRS.intersection(path.relative_to(folder).parts):
            yield path


def _tokens(paths: Iterator[Path]) -> int:
    return -(-sum(path.stat().st_size for path in paths) // CHARS_PER_TOKEN)


def folder_tokens(folder: Path) -> int:
    """The tokens every file under `folder` costs to read, outside the tool and dependency folders."""
    return _tokens(countable_files(folder))


def source_and_book_tokens(source: int, book: int) -> int:
    """What a writer holds of the source and the book: the source read twice, and twice the larger of the book on disk and the book it will write."""
    return SOURCE_READS * source + BOOK_HOLDS * max(book, BOOK_PER_SOURCE_TOKEN * source)


def ceiling_blocker_reason(tokens: int) -> str | None:
    """Why a writer is not sent `tokens` of source and book, or None when they fit."""
    if tokens <= SOURCE_AND_BOOK_CEILING_TOKENS:
        return None
    return (
        f"the source and the book the writer reads and writes are about {tokens} tokens, over the {SOURCE_AND_BOOK_CEILING_TOKENS} "
        + f"a writer reads beside the {PROMPT_AND_SKILL_ALLOWANCE_TOKENS} of its prompt and skill, "
        + f"the {OPERATOR_ANSWER_ALLOWANCE_TOKENS} of the operator's answer, "
        + f"the {CHECK_AND_SCENARIO_ALLOWANCE_TOKENS} of its check and scenario runs, the {OSTLER_ALLOWANCE_TOKENS} of its ostler runs "
        + f"and the {STEP_ALLOWANCE_TOKENS} of its {WRITER_STEPS} steps: split the surface"
    )
