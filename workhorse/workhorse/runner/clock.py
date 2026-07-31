"""Wall-clock time and waiting, as a dependency the ladder is handed."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """The passage of time, as the recovery ladder and the streaming loop need it.

    Three operations, because between them they do exactly three things with time.
    The ladder asks what time it is (to say when a cap window reopens) and waits
    (for the cap, for a backoff, for the pause before a reframe); a run that sleeps
    through an eight-hour cap is then a test that costs microseconds, with nothing
    patched. The streaming loop asks how long the turn has been running.

    ``monotonic`` is separate from ``now`` rather than derived from it because a
    turn's deadline must not move when the wall clock does. ``now`` is a date an
    operator reads ("resuming around 11:30am") and is allowed to jump under NTP;
    ``monotonic`` is a duration a timeout is measured against and never goes
    backwards. Collapsing the two would make an NTP correction mid-turn either
    expire a healthy turn or extend a wedged one.
    """

    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """The real clock — the only implementation that actually waits.

    Field-less on purpose: it exists to be substitutable, which is what earns a
    class here, and the state it stands in for belongs to the operating system.
    """

    def now(self) -> datetime:
        return datetime.now()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


#: The default clock. One instance because it holds nothing; injected, never imported
#: by the code that waits.
SYSTEM_CLOCK = SystemClock()
