"""What an operator wrote under a question on a gate file."""
from __future__ import annotations

from workhorse import gates


def answer_below(text: str, question: str, limit: int) -> str:
    """What the operator wrote under *question* on the gate *text*, cut to *limit* characters. A gate whose newest question is not *question* holds no answer to it."""
    asked = question.strip()
    latest = gates.latest_question(text, limit=len(asked) + limit)
    if not asked or not latest.startswith(asked):
        return ""
    return latest[len(asked):].removesuffix(gates.TRUNCATION_NOTE).strip()


__all__ = ["answer_below"]
