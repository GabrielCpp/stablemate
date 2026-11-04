"""What an operator wrote under a question on a gate file."""
from __future__ import annotations

from workhorse_workflows.kit import answer

ANSWER_LIMIT_CHARS = 8000


def answer_below(text: str, question: str) -> str:
    """What the operator wrote under *question* on the gate *text*, or nothing when a newer question replaced it."""
    return answer.answer_below(text, question, ANSWER_LIMIT_CHARS)


__all__ = ["ANSWER_LIMIT_CHARS", "answer_below"]
