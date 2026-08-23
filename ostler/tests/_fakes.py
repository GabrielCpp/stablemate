"""Test doubles for the ports ostler is handed rather than reaches for."""

from __future__ import annotations

from datetime import datetime, timedelta


class FakeClock:
    """A ``stablemate_core.clock.Clock`` that records what it was asked to wait and never waits.

    The stack supervisor polls: a boot window, a health gate that retries every five
    seconds for two minutes, a stop recipe with a ceiling. Injecting time makes each of
    those a list of numbers to assert on rather than a test that actually sleeps through
    them, and ``slept`` is what says the caller backed off the interval it documented.

    Sleeping advances both ``now`` and ``monotonic``, because a deadline is measured
    against one and a timestamp read off the other.
    """

    def __init__(self, now: datetime | None = None) -> None:
        # A fixed, unremarkable instant so a test that prints a time reads the same on
        # every machine; tests that care state their own.
        self._now = now or datetime(2026, 1, 1, 12, 0, 0)
        self._elapsed = 0.0
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        """Elapsed seconds since this clock's own zero, moved only by ``sleep``.

        Deliberately not derived from the wall clock a test may have set to an arbitrary
        instant: what a caller measures with this is a duration, so it starts at zero and
        advances only when the test says time passed.
        """
        return self._elapsed

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self._elapsed += seconds
        self._now += timedelta(seconds=seconds)
