"""Scripted replies for the PM's turns, built from the angle catalog."""

from __future__ import annotations

from typing import Any

from workhorse_workflows.author.pm.angles import ANGLES


def verdict(stage: str, failing: dict[str, str] | None = None) -> dict[str, Any]:
    """A complete review reply for *stage*: each angle passes unless *failing* names it."""
    failing = failing or {}
    entries: list[dict[str, Any]] = []
    for angle in ANGLES[stage]:
        if angle.name in failing:
            entries.append(
                {
                    "angle": angle.name,
                    "status": "failed",
                    "findings": [
                        {
                            "target": "the subject",
                            "issue": failing[angle.name],
                            "repair": "repair it",
                        }
                    ],
                }
            )
        else:
            entries.append({"angle": angle.name, "status": "passed", "findings": []})
    return {"angles": entries}


def answer(text: str = "decided") -> dict[str, str]:
    """A gap-answer reply that settles the question itself."""
    return {"kind": "answered", "answer": text, "reason": ""}


def amendment(reason: str = "the milestone must change") -> dict[str, str]:
    """A gap-answer reply that needs the operator."""
    return {"kind": "amendment", "answer": "", "reason": reason}
