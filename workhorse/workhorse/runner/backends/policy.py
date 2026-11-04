"""The guard policy a confined turn of the claude or codex CLI is held to."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path

from workhorse.runner.backends import AgentProfile, operator_config_dirs
from workhorse.runner.backends.guard import Policy


def confined_policy(
    agent: AgentProfile | None,
    cwd: str | None,
    add_dirs: list[str] | None,
    harness: str,
    skill_roots: Callable[[Path], Sequence[Path]],
) -> Policy | None:
    """What the guard holds a confined turn to: its cwd, the dirs it reads and its commands. None for a turn that is not confined."""
    if agent is None or not agent.confined:
        return None
    turn_cwd = Path(cwd or os.getcwd()).resolve()
    roots = (
        turn_cwd,
        *(Path(directory).resolve() for directory in add_dirs or []),
        *skill_roots(turn_cwd),
        *operator_config_dirs(harness),
    )
    return Policy(cwd=turn_cwd, read_roots=tuple(dict.fromkeys(roots)), commands=tuple(agent.commands))
