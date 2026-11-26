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


_LEAD = r"(?:resets?(?:\s+at)?|try\s+again\s+at)\s+"
_DATE = (
    r"(?:(?P<month>[a-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(?P<year>\d{4}))?,?\s+(?:at\s+)?)?"
)
_CLOCK_12H = re.compile(
    _LEAD + _DATE + r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>[ap]m)", re.IGNORECASE
)
_CLOCK_24H = re.compile(_LEAD + _DATE + r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\b", re.IGNORECASE)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def parse_reset_seconds(text: str, now: datetime) -> float | None:
    """Seconds from ``now`` until the cap reset time named in ``text``, such as "resets 3pm" or "try again at 3:40 PM"."""
    m = _CLOCK_12H.search(text)
    if m:
        hour = int(m.group("hour")) % 12
        if m.group("meridiem").lower() == "pm":
            hour += 12
    else:
        m = _CLOCK_24H.search(text)
        if not m:
            return None
        hour = int(m.group("hour"))
    minute = int(m.group("minute") or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if m.group("month"):
        month = m.group("month").lower()
        if month not in _MONTHS:
            return None
        year = int(m.group("year") or now.year)
        try:
            target = target.replace(
                year=year, month=_MONTHS.index(month) + 1, day=int(m.group("day"))
            )
        except ValueError:
            return None
        if not m.group("year") and target <= now:
            try:
                target = target.replace(year=year + 1)
            except ValueError:
                return None
        return max((target - now).total_seconds(), 0.0) or None
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
