"""The budgets and bounds every lane's owner turn runs under."""
from __future__ import annotations

from workhorse.runner.backends import AgentProfile

UNBOUNDED = float("inf")

SILENCE_S = 1800.0

COMMAND_CAP_S = 1500

HUMAN_MODES = frozenset({"human", "operator"})

MAX_BLOCKS = 3

MAX_LAPS = 3


def owner_profile(lane: str) -> AgentProfile:
    """The agent profile of one lane's owner, with the command cap every lane shares."""
    return AgentProfile(name=f"coder-{lane}", command_timeout_s=COMMAND_CAP_S)


__all__ = [
    "COMMAND_CAP_S",
    "HUMAN_MODES",
    "MAX_BLOCKS",
    "MAX_LAPS",
    "SILENCE_S",
    "UNBOUNDED",
    "owner_profile",
]
