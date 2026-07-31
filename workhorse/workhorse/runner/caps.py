"""How long to wait out a scheduled-reset cap, and how to sleep it visibly."""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from workhorse import otel
from workhorse.config_run import AgentResilience
from workhorse.runner.failure import BackendInvocationError


def parse_reset_seconds(text: str, now: datetime | None = None) -> float | None:
    """Seconds from ``now`` until the cap reset time named in ``text`` — e.g.
    'resets 3:50am', 'resets at 11pm', 'resets 15:50'. Returns the next future
    occurrence of that clock time, or None if no time is found (caller defaults)."""
    now = now or datetime.now()
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
    now: float | None = None,
    *,
    resilience: AgentResilience,
) -> tuple[float, str]:
    """How long to sleep for a cap, and a human 'resuming around' label.

    Prefers the structured ``reset_at`` epoch (precise, timezone-correct) when the
    error carries one, bounded by ``resilience.cap_max_wait_s``; otherwise parses
    a reset time from the message text; otherwise uses the default wait.
    """
    now = now if now is not None else time.time()
    if exc.reset_at is not None:
        secs = exc.reset_at - now
        if secs > 0:
            delay = min(secs, resilience.cap_max_wait_s) + resilience.cap_wait_margin_s
            when = datetime.fromtimestamp(now + delay).strftime("%a %H:%M")
            return delay, when
        # Reset already passed (stale event / clock skew) → retry promptly.
        return resilience.cap_wait_margin_s, "reset already passed — retrying shortly"

    parsed = parse_reset_seconds(str(exc))
    if parsed is None:
        return resilience.cap_default_wait_s, "unknown reset — using default wait"
    delay = parsed + resilience.cap_wait_margin_s
    return delay, (datetime.now() + timedelta(seconds=delay)).strftime("%a %H:%M")


def sleep_with_notice(
    total_s: float,
    node_id: str,
    label: str,
    *,
    resilience: AgentResilience,
) -> None:
    """Sleep ``total_s`` seconds, printing a 'still paused' line every
    ``resilience.cap_tick_s``
    so a long, legitimate wait can't be mistaken for a hang. Each tick also emits
    the cap-wait heartbeat metric — the external liveness proof that lets a
    collector tell a legitimate multi-day cap sleep from an actual hang."""
    remaining = total_s
    otel.heartbeat(node_id, remaining)
    while remaining > 0:
        chunk = min(remaining, resilience.cap_tick_s)
        time.sleep(chunk)
        remaining -= chunk
        otel.heartbeat(node_id, remaining)
        if remaining > 0:
            print(
                f"[{node_id}] ⏸ still paused ({label}); ~{int(remaining)}s remaining",
                flush=True,
            )
