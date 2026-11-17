"""What a run says on stderr while it plays, and the verdict block it ends its stdout with."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import TextIO

from ostler.book.defects import tally
from ostler.book.journey import JourneyResult

CLOCK: Callable[[], float] = time.monotonic
NAMED_FAILURES = 50


class Progress:
    """Writes one flushed line to its stream as each journey ends and as each phase starts and ends."""

    def __init__(self, stream: TextIO | None = None, clock: Callable[[], float] | None = None) -> None:
        self.stream = stream
        self.clock = clock

    def now(self) -> float:
        return (self.clock or CLOCK)()

    def say(self, line: str) -> None:
        out = self.stream or sys.stderr
        out.write(line + "\n")
        out.flush()

    def journey(self, at: int, total: int, name: str, verdict: str, started: float) -> None:
        self.say(f"[{at}/{total}] {name} {verdict} {self.now() - started:.1f}s")

    def phase(self, name: str) -> float:
        self.say(f"{name}: start")
        return self.now()

    def done(self, name: str, started: float) -> None:
        self.say(f"{name}: end {self.now() - started:.1f}s")


def verdict_lines(results: list[JourneyResult], red: list[str]) -> list[str]:
    """The counts of the run, the parts that made it red, and the name of each failing journey, at most `NAMED_FAILURES` of them."""
    failing = [r for r in results if not r.ok]
    lines = ["verdict", tally(results), f"red: {', '.join(red)}" if red else "green"]
    lines += [f"FAIL  {r.journey.title()}" for r in failing[:NAMED_FAILURES]]
    if len(failing) > NAMED_FAILURES:
        lines.append(f"and {len(failing) - NAMED_FAILURES} more failing journeys")
    return lines
