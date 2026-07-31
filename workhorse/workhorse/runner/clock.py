"""Wall-clock time and waiting, as a dependency the ladder is handed."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """The passage of time, as the recovery ladder needs it.

    Two operations, because the ladder does exactly two things with time: it asks
    what time it is (to say when a cap window reopens) and it waits (for the cap,
    for a backoff, for the pause before a reframe). A run that sleeps through an
    eight-hour cap is then a test that costs microseconds, with nothing patched.
    """

    def now(self) -> datetime: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """The real clock — the only implementation that actually waits.

    Field-less on purpose: it exists to be substitutable, which is what earns a
    class here, and the state it stands in for belongs to the operating system.
    """

    def now(self) -> datetime:
        return datetime.now()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


#: The default clock. One instance because it holds nothing; injected, never imported
#: by the code that waits.
SYSTEM_CLOCK = SystemClock()
