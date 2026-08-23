"""Wall-clock time and waiting, as a dependency rather than an ambient call."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """The passage of time, as anything that waits on it needs it.

    Three operations, because between them they do exactly three things with time:
    ask what time it is (to say when a window reopens), wait (for a cap, a backoff,
    a health poll), and ask how long something has been running. Handing those in
    rather than calling `time` directly is what makes a test of an eight-hour wait
    cost microseconds with nothing patched.

    ``monotonic`` is separate from ``now`` rather than derived from it because a
    deadline must not move when the wall clock does. ``now`` is a date an operator
    reads ("resuming around 11:30am") and is allowed to jump under NTP;
    ``monotonic`` is a duration a timeout is measured against and never goes
    backwards. Collapsing the two would make an NTP correction mid-wait either
    expire a healthy deadline or extend a wedged one.
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
