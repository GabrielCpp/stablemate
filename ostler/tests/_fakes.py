"""Test doubles for the ports ostler is handed rather than reaches for."""

from __future__ import annotations

from datetime import datetime, timedelta


class FakeClock:
    """A ``stablemate_core.clock.Clock`` that records what it was asked to wait and never waits."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 1, 1, 12, 0, 0)
        self._elapsed = 0.0
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        """Elapsed seconds since this clock's own zero, moved only by ``sleep``."""
        return self._elapsed

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self._elapsed += seconds
        self._now += timedelta(seconds=seconds)
