"""`turn.json`: what one agent turn was started with, enough to start it again."""

from __future__ import annotations

from pydantic import BaseModel, Field

from workhorse.records import TreeStart
from workhorse.runner.backends import AgentProfile


class TurnRecord(BaseModel):
    """One agent turn's settings and the working trees it started from."""

    node: str = ""
    backend: str = ""
    profile: str = ""
    power: str | None = None
    model: str | None = None
    effort: str | None = None
    timeout_s: float | None = None
    base_timeout_s: float | None = None
    timeout_scale: float = 1.0
    cwd: str | None = None
    add_dirs: list[str] = Field(default_factory=list)
    agent: AgentProfile | None = None
    session_chain: str = ""
    resumed_session: bool = False
    start: list[TreeStart] = Field(default_factory=list)


def parse_turn_record(text: str) -> TurnRecord:
    """Parse a `turn.json` body."""
    return TurnRecord.model_validate_json(text)
