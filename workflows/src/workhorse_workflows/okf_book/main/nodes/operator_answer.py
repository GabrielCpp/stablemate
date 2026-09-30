"""The operator's latest answer, kept beside the run's records so every repair turn reads it until the next gate."""
from __future__ import annotations

from pathlib import Path

from workhorse import gates

ANSWER_NAME = "operator-answer.md"


def answer_below(gate: str, question: str) -> str:
    """What the operator wrote under *question* on *gate*. A gate whose newest question is not *question* holds no answer to it."""
    latest = gates.latest_question(gate, limit=len(gate))
    asked = question.strip()
    if not asked or not latest.startswith(asked):
        return ""
    return latest[len(asked):].strip()


def write_answer(records_dir: Path, answer: str) -> None:
    """Keep *answer* as the one the repair turns read, replacing the last."""
    records_dir.mkdir(parents=True, exist_ok=True)
    _ = (records_dir / ANSWER_NAME).write_text(f"{answer.strip()}\n" if answer.strip() else "", encoding="utf-8")


def read_answer(records_dir: Path) -> str:
    """The answer the repair turns read, or ``""`` when the operator has given none."""
    path = records_dir / ANSWER_NAME
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""
