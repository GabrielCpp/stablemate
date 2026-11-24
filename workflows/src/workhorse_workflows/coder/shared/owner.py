"""The budgets and bounds every lane's owner turn runs under."""
from __future__ import annotations

from workhorse.pyflow import AgentTimeout
from workhorse.runner.backends import AgentProfile

TURN_MINUTES = 180

REVIEW_MINUTES = 20

SILENCE_S = 1800.0

COMMAND_CAP_S = 1500

HUMAN_MODES = frozenset({"human", "operator"})

MAX_BLOCKS = 3

MAX_LAPS = 3


def turn_seconds(minutes: int) -> float:
    """The wall-clock allowance of one owner turn, in seconds, from its `turn_minutes`."""
    return minutes * 60.0


def cut_notes(turn: str, exc: AgentTimeout, allowance: str = "turn_minutes") -> str:
    """What the operator reads when a turn was cut: the time allowance that ran out, or the silence that spent its retries."""
    if exc.deadline_s is not None:
        minutes = max(1, round(exc.deadline_s / 60))
        return (
            f"{turn} was cut after {minutes} minutes, its time allowance (`{allowance}`).\n\n"
            "Its session is kept. Answer here and the turn starts again on the same session, "
            "with your answer in hand."
        )
    return (
        f"{turn} went quiet, was cut, and its retries are spent: {exc}\n\n"
        "Answer here and the turn starts again, with your answer in hand."
    )


def owner_profile(lane: str) -> AgentProfile:
    """The agent profile of one lane's owner, with the command cap every lane shares."""
    return AgentProfile(name=f"coder-{lane}", command_timeout_s=COMMAND_CAP_S)


__all__ = [
    "COMMAND_CAP_S",
    "HUMAN_MODES",
    "MAX_BLOCKS",
    "MAX_LAPS",
    "REVIEW_MINUTES",
    "SILENCE_S",
    "TURN_MINUTES",
    "cut_notes",
    "owner_profile",
    "turn_seconds",
]
