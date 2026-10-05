"""The operator's latest answer, kept beside the run's records so each book's owner reads it on its next turn, and not again."""
from __future__ import annotations

from pathlib import Path

from workhorse import gates
from workhorse_workflows.okf_book.main.nodes.turn_budget import CHARS_PER_TOKEN, OPERATOR_ANSWER_ALLOWANCE_TOKENS

ANSWER_NAME = "operator-answer.md"
HEARD_NAME = "operator-answer.heard"
ANSWER_LIMIT_CHARS = OPERATOR_ANSWER_ALLOWANCE_TOKENS * CHARS_PER_TOKEN


def answer_below(text: str, question: str) -> str:
    """What the operator wrote under *question* on the gate *text*, cut to the repair turn's allowance for it. A gate whose newest question is not *question* holds no answer to it."""
    asked = question.strip()
    latest = gates.latest_question(text, limit=len(asked) + ANSWER_LIMIT_CHARS)
    if not asked or not latest.startswith(asked):
        return ""
    return latest[len(asked):].removesuffix(gates.TRUNCATION_NOTE).strip()


def write_answer(records_dir: Path, answer: str) -> None:
    """Keep *answer* as the one the owners read, replacing the last, with no owner having read it yet."""
    records_dir.mkdir(parents=True, exist_ok=True)
    _ = (records_dir / ANSWER_NAME).write_text(f"{answer.strip()}\n" if answer.strip() else "", encoding="utf-8")
    (records_dir / HEARD_NAME).unlink(missing_ok=True)


def _heard(records_dir: Path) -> set[str]:
    path = records_dir / HEARD_NAME
    return set(path.read_text(encoding="utf-8").split()) if path.is_file() else set()


def read_answer(records_dir: Path, service: str) -> str:
    """The answer *service*'s owner has still to read, or ``""`` when the operator has given none or that owner already replied after reading it."""
    path = records_dir / ANSWER_NAME
    if service in _heard(records_dir) or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def mark_heard(records_dir: Path, service: str) -> None:
    """Record that *service*'s owner replied to a turn that carried the answer, so its later turns open without it."""
    if not read_answer(records_dir, service):
        return
    _ = (records_dir / HEARD_NAME).write_text("".join(f"{name}\n" for name in sorted({*_heard(records_dir), service})), encoding="utf-8")
