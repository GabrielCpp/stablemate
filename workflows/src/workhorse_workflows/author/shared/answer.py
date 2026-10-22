"""What an operator wrote under a question on a gate file."""
from __future__ import annotations

from workhorse import gates

ANSWER_LIMIT_CHARS = 8000


def answer_below(text: str, question: str) -> str:
    """What the operator wrote under *question* on the gate *text*, or nothing when a newer question replaced it."""
    asked = question.strip()
    latest = gates.latest_question(text, limit=len(asked) + ANSWER_LIMIT_CHARS)
    if not asked or not latest.startswith(asked):
        return ""
    return latest[len(asked):].removesuffix(gates.TRUNCATION_NOTE).strip()


__all__ = ["ANSWER_LIMIT_CHARS", "answer_below"]
