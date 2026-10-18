from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

STALE_AFTER_MS = 15000
OFFLINE_AFTER_MS = 60000
RESYNC_EVERY_S = 5.0
EVAL_EVERY_S = 1.0
BACKOFF_BASE_S = 0.5
BACKOFF_MAX_S = 30.0

Phase = Literal["live", "stale", "reconnecting", "offline"]


@dataclass(frozen=True)
class Observation:
    now: float
    socket_open: bool
    last_message_ts: float
    closed_since: float


@dataclass(frozen=True)
class Connection:
    phase: Phase
    resyncing: bool


def derive_connection(obs: Observation) -> Connection:
    if obs.socket_open:
        if obs.now - obs.last_message_ts <= STALE_AFTER_MS:
            return Connection("live", False)
        return Connection("stale", True)
    if obs.now - obs.closed_since <= OFFLINE_AFTER_MS:
        return Connection("reconnecting", True)
    return Connection("offline", True)


def backoff_delay(attempt: int) -> float:
    return min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2**attempt)
