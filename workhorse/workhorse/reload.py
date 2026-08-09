"""The reload request: a file an operator writes, and the run picks up mid-turn.

An operator watching a live run sees the flow is broken — a prompt that sends the agent
in circles, a gate handing back the same worklist — and pushes the fix. What they need
next is for the turn that is *currently* burning tokens against the old code to stop and
re-enter against the new code. A turn can last hours, so honouring the request at the
next state boundary would deliver hours of exactly the waste the operator is stopping.

Hence a request that the stream loop can see: the request is a small JSON file in the run
dir, written atomically so a half-written one is never observed, and the loop that already
wakes once a second to check the wall clock also stats this path. The transport is a file
rather than a signal because it survives the operator's shell exiting, carries flags, and
needs no pid — and because the control server in the control-loop plan can later write the
same file without this module changing.

Nothing here kills anything. This module only says whether a request is outstanding and
what it asked for; acting on it belongs to the stream loop and the driver, which is also
what keeps this importable from a test with no run in flight.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REQUEST_FILE = "reload-request.json"

logger = logging.getLogger(__name__)


class ReloadRequested(Exception):
    """An operator asked for pushed code to be picked up. Not a verdict, not a failure.

    It travels as an exception because it has to unwind an arbitrarily deep stack of nested
    `drive` frames — `drive` is re-entrant, and swapping modules under a live parent frame
    would hand new-class objects to old-class validation. But it is the opposite of a
    failure in every way the retry ladder cares about: the turn it interrupted was cut on
    purpose, so it consumes no short retry, no reframe and no compaction attempt, and enters
    no backoff. Misclassifying it as a timeout would prepend an overran-your-budget warning
    to a prompt that overran nothing; misclassifying it as a hard failure would spend a
    reframe on a turn nobody was unhappy with.

    Not a `PyflowError`: it is raised in `runner/`, which imports nothing from `pyflow/`,
    and inverting that edge to reuse a base class would be the more expensive mistake. Like
    `RunBudgetExceeded` it stamps no terminal — the run stopped, it did not decide — and
    unlike it the stop is not the end: the driver re-enters from the checkpoint the state
    already wrote on entry, in the same process.
    """

    def __init__(self, message: str = "reload requested", *, core: bool = False) -> None:
        super().__init__(message)
        self.core = core


class _Watch:
    """The run dir the stream loop polls, set once when the run starts.

    Process-wide because there is one run per process and the stream loop is several
    layers below anything that knows where its artifacts live — the same reason
    `runner/process.py` holds one module-level `ProcessSupervisor`. An object rather than
    a bare global so a test can set and clear it without rebinding a module attribute.
    """

    run_dir: Path | None = None


_watch = _Watch()


def arm(run_dir: str | Path | None) -> None:
    """Point the poll at this run's directory. Idempotent; `None` disarms."""
    _watch.run_dir = Path(run_dir) if run_dir else None


def armed() -> Path | None:
    return _watch.run_dir


def armed_pending() -> "ReloadRequest | None":
    """The outstanding request for the armed run, or None when nothing is armed.

    This is what the stream loop calls once per select slice. With nothing armed it is a
    branch on an attribute, so an unarmed process — every unit test that streams a fake
    agent — pays nothing.
    """
    return pending(_watch.run_dir)


@dataclass(frozen=True)
class ReloadRequest:
    """What an operator asked for, as recorded in the request file.

    `at_boundary` is the non-default because the default reason for reloading is that the
    turn is broken. A turn 95% through expensive work that is *not* broken is the case
    `at_boundary` exists for, and it is worth having to ask for.
    """

    core: bool = False
    at_boundary: bool = False
    requested_at: str = ""

    @property
    def cuts_the_turn(self) -> bool:
        return not self.at_boundary


def request(run_dir: str | Path, *, core: bool = False, at_boundary: bool = False) -> Path:
    """Write the request atomically, and return the path written.

    `os.replace` on the same filesystem is what makes a concurrently polling reader see
    either the previous request or this one, never a truncated file. Overwriting an
    outstanding request is deliberate: the newest flags win, and two operators asking for
    a reload want one reload.
    """
    directory = Path(run_dir)
    path = directory / REQUEST_FILE
    payload = {
        "core": core,
        "at_boundary": at_boundary,
        "requested_at": datetime.now(UTC).isoformat(),
    }
    tmp = directory / f".{REQUEST_FILE}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)
    return path


def pending(run_dir: str | Path | None) -> ReloadRequest | None:
    """The outstanding request, or None. Never raises — a poll is not a failure point.

    A malformed or vanished file reads as "no request": the poll runs inside the stream
    loop of a live agent turn, and a reload that could not be parsed must not be the thing
    that ends the run.
    """
    if not run_dir:
        return None
    path = Path(run_dir) / REQUEST_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("ignoring unreadable reload request at %s: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        logger.warning("ignoring reload request at %s: not a JSON object", path)
        return None
    return ReloadRequest(
        core=bool(raw.get("core", False)),
        at_boundary=bool(raw.get("at_boundary", False)),
        requested_at=str(raw.get("requested_at", "")),
    )


def consume(run_dir: str | Path | None) -> ReloadRequest | None:
    """Read the request and remove it, so one request produces exactly one reload.

    Removal happens *before* the caller acts on it. The alternative — clear it after the
    swap succeeded — turns a reload onto a tree that does not import into a loop that
    re-reads the same request forever, which is the one failure mode a reload must not
    have.
    """
    found = pending(run_dir)
    if found is None:
        return None
    try:
        (Path(run_dir or ".") / REQUEST_FILE).unlink()
    except OSError as exc:  # pragma: no cover - the read above already proved it is there
        logger.warning("could not clear the reload request: %s", exc)
    return found


__all__ = [
    "REQUEST_FILE",
    "ReloadRequest",
    "ReloadRequested",
    "arm",
    "armed",
    "armed_pending",
    "consume",
    "pending",
    "request",
]
