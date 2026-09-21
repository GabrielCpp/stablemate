"""How long to wait out a scheduled-reset cap, and how to sleep it visibly."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta

from workhorse import otel
from workhorse.config_run import AgentResilience
from workhorse.control import NULL_CHANNEL, ControlChannel, Request, wait_until
from workhorse._vendor.stablemate_core.clock import Clock
from workhorse.runner.failure import BackendInvocationError


def parse_reset_seconds(text: str, now: datetime) -> float | None:
    """Seconds from ``now`` until the cap reset time named in ``text`` — e.g."""
    m = re.search(r"resets?(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)", text, re.IGNORECASE)
    if m:
        hour = int(m.group(1)) % 12
        if m.group(3).lower() == "pm":
            hour += 12
        minute = int(m.group(2) or 0)
    else:
        m = re.search(r"resets?(?:\s+at)?\s+(\d{1,2}):(\d{2})\b", text, re.IGNORECASE)
        if not m:
            return None
        hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def cap_delay_seconds(
    exc: BackendInvocationError,
    *,
    resilience: AgentResilience,
    clock: Clock,
) -> tuple[float, str]:
    """How long to sleep for a cap, and a human 'resuming around' label."""
    now = clock.now()
    if exc.reset_at is not None:
        secs = exc.reset_at - now.timestamp()
        if secs > 0:
            delay = min(secs, resilience.cap_max_wait_s) + resilience.cap_wait_margin_s
            when = (now + timedelta(seconds=delay)).strftime("%a %H:%M")
            return delay, when
        return resilience.cap_wait_margin_s, "reset already passed — retrying shortly"

    parsed = parse_reset_seconds(str(exc), now)
    if parsed is None:
        return resilience.cap_default_wait_s, "unknown reset — using default wait"
    delay = parsed + resilience.cap_wait_margin_s
    return delay, (now + timedelta(seconds=delay)).strftime("%a %H:%M")


def sleep_with_notice(
    total_s: float,
    node_id: str,
    label: str,
    *,
    resilience: AgentResilience,
    clock: Clock,
    channel: ControlChannel = NULL_CHANNEL,
    honour: Callable[[Request], Request | None] = lambda request: request,
) -> Request | None:
    """Sleep ``total_s`` seconds, printing a 'still paused' line every ``resilience.cap_tick_s`` so a long, legitimate wait can't be mistaken for a hang."""
    remaining = total_s
    otel.heartbeat(node_id, remaining)
    while remaining > 0:
        chunk = min(remaining, resilience.cap_tick_s)
        request = wait_until(None, timeout=chunk, clock=clock, channel=channel, tick=chunk)
        if request is not None:
            honoured = honour(request)
            if honoured is not None:
                return honoured
            continue
        remaining -= chunk
        otel.heartbeat(node_id, remaining)
        if remaining > 0:
            print(
                f"[{node_id}] ⏸ still paused ({label}); ~{int(remaining)}s remaining",
                flush=True,
            )
