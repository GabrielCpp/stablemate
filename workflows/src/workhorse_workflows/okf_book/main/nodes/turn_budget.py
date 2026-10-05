"""What one owner turn is allowed beside the source and the book: the prompt and the format skill, the operator's latest answer, and the steps it takes."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

CHARS_PER_TOKEN = 4
PROMPT_AND_SKILL_ALLOWANCE_TOKENS = 80_000
OPERATOR_ANSWER_ALLOWANCE_TOKENS = 2_000
WRITER_STEPS = 200
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

