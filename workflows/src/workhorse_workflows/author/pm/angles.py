"""The angles the PM judges each stage's output from, one prompt file per angle."""
from __future__ import annotations

from dataclasses import dataclass

PROMPTS = "pm/prompts"


@dataclass(frozen=True)
class Angle:
    """One question the PM asks of a stage's output."""

    name: str
    prompt: str


def _angles(stage: str, *names: str) -> tuple[Angle, ...]:
    return tuple(Angle(name, f"{PROMPTS}/angles/{stage}/{name}.md") for name in names)


ANGLES: dict[str, tuple[Angle, ...]] = {
    "epic-split": _angles("epic-split", "coverage", "boundaries", "order", "scope"),
    "story-split": _angles("story-split", "coverage", "vertical", "order", "services"),
    "story": _angles(
        "story", "journey", "chrome", "transient-feedback", "grounding", "mockup"
    ),
    "epic-edit-plan": _angles("epic-edit-plan", "plan"),
}


def stage_prompt(stage: str) -> str:
    """The prompt file that briefs the PM on what *stage* produced."""
    return f"{PROMPTS}/stages/{stage}.md"


__all__ = ["ANGLES", "Angle", "stage_prompt"]
