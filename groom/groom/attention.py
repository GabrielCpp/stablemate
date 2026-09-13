"""Wire records shared by groom's attention producer and waiting CLI."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

EventName = Literal["blocked", "ended", "stuck", "stalled", "gave-up", "churn", "watchdog", "died", "waiting"]
RULE_EVENTS: dict[str, EventName] = {
    "BLOCKED": "blocked", "ENDED": "ended", "STUCK": "stuck", "STALL": "stalled",
    "GAVE-UP": "gave-up", "CHURN": "churn", "WATCHDOG": "watchdog", "DIED": "died",
    "WAITING": "waiting",
}
DEFAULT_EVENTS = "blocked,ended,stuck,stalled,gave-up"


class AttentionEvent(BaseModel):
    run_id: str
    event: EventName
    node: str = ""
    question: str = ""
    gate_path: str = ""
    terminal: str = ""
    message: str = ""


class AttentionFrame(BaseModel):
    type: Literal["attention"] = "attention"
    events: list[AttentionEvent]


class StateAttention(BaseModel):
    type: Literal["state"]
    attention: list[AttentionEvent]
