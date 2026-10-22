"""The PM ledger: every product question answered for a milestone, in the order it was answered."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

HEADING = "# PM answers"


def ledger_entry(asker: str, question: str, answer: str, by: Literal["pm", "human"]) -> str:
    """One entry, as the ledger spells it."""
    return (
        f"\n## {asker}\n\n"
        f"- **Answered by**: {by}\n\n"
        f"**Question**\n\n{question.strip()}\n\n"
        f"**Answer**\n\n{answer.strip()}\n"
    )


def append_entry(
    ledger: Path, asker: str, question: str, answer: str, by: Literal["pm", "human"]
) -> None:
    """Append one entry, creating the ledger with its heading when it is missing."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
    head = "" if existing.strip() else f"{HEADING}\n"
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(head + ledger_entry(asker, question, answer, by))


__all__ = ["HEADING", "append_entry", "ledger_entry"]
