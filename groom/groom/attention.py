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


class Standing(BaseModel):
    node: str = ""
    node_elapsed_s: float = 0.0
    turn_active: bool | None = None
    turn_elapsed_s: float = 0.0
    turn_idle_s: float = 0.0
    wait_kind: str = ""
    wait_elapsed_s: float = 0.0
    gas: float | None = None
    alive: bool = False
    terminal: str = ""
    wait_gate_question: str = ""
    wait_gate_path: str = ""


class NodeVisit(BaseModel):
    node: str
    visits: int = 0
    turns: int = 0
    cost_usd: float = 0.0
    output_tokens: int = 0


class Lap(BaseModel):
    node: str
    work_id: str
    turns: int


class Gate(BaseModel):
    kind: str
    node: str = ""
    outcome: str = ""
    question: str = ""


class LogLine(BaseModel):
    ts: float
    level: str
    node: str = ""
    message: str = ""


class Window(BaseModel):
    nodes: list[NodeVisit] = []
    laps: list[Lap] = []
    gates: list[Gate] = []
    events: list[AttentionEvent] = []
    warnings: list[LogLine] = []
    cost_usd: float = 0.0
    output_tokens: int = 0
    turns: int = 0


class EventFrame(BaseModel):
    type: Literal["event"] = "event"
    seq: int
    ts: float
    event: AttentionEvent


class DigestFrame(BaseModel):
    type: Literal["digest"] = "digest"
    seq: int
    ts: float
    since: float
    until: float
    quiet: bool
    summary: str
    standing: Standing
    window: Window
