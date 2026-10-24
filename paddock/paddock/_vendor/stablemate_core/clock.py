"""Wall-clock time and waiting, as a dependency rather than an ambient call."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """The passage of time, as anything that waits on it needs it."""

    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """The real clock — the only implementation that actually waits."""

    def now(self) -> datetime:
        return datetime.now()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


SYSTEM_CLOCK = SystemClock()
