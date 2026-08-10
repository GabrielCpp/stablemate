"""The reload verb: what an operator's request means to a run that is already going.

An operator watching a live run sees the flow is broken — a prompt that sends the agent
in circles, a gate handing back the same worklist — and pushes the fix. What they need
next is for the turn that is *currently* burning tokens against the old code to stop and
re-enter against the new code. A turn can last hours, so honouring the request at the
next state boundary would deliver hours of exactly the waste the operator is stopping.

The request itself arrives on :mod:`workhorse.control` — one socket, shared with every
other verb. What lives here is only what `reload` *means*: which of the two sites that
can honour one does, and what a request that is not a reload gets told. The stream loop
cuts a turn that is burning tokens; the state boundary catches every other moment, and
also the `--at-boundary` request the stream loop deliberately declines.

Nothing here kills anything. This module says whether a reload is outstanding and what it
asked for; acting on it belongs to the stream loop and the driver, which is also what
keeps this importable from a test with no run in flight.
"""

from __future__ import annotations

import logging

from workhorse import control
from workhorse.control import Request

#: What a run exits with when a `--core` reload could not replace the process image
#: itself, and a supervisor should start it again. Chosen to sit outside the normal
#: 0/1/2, 126/127 and 128+signal ranges, and shared with the two other processes that
#: already spell a reload this way (`supervisor.py`, `groom/groom/sidecar.py`), so one
#: supervision loop can serve all three. Any other code means stop, which is what keeps
#: a reload onto code that does not import from storming.
RELOAD_EXIT_CODE = 3

ACTION = "reload"

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


def cut_requested() -> Request | None:
    """A reload the streaming turn should be cut for, or None. Never raises.

    This is what the stream loop calls once per select slice, so every way of not being a
    cut is answered here rather than upstack: another verb is declined, and an
    `--at-boundary` reload is acknowledged and *held* for the state boundary — taking it
    off the socket consumed it, so declining to act on it means remembering it.
    """
    return cut_by(control.take())


def cut_by(request: Request | None) -> Request | None:
    """The same policy, for a request some other wait already took off the channel.

    A cap wait sleeps for days and wakes on a message, so it holds the request rather
    than the channel by the time a decision is due. Splitting the judgement from the
    taking is what keeps that site and the stream loop deciding identically instead of
    growing a second, quietly divergent copy of this.
    """
    if request is None:
        return None
    if request.action != ACTION:
        control.answer({"error": f"this run does not know the action {request.action!r}"})
        logger.warning("ignoring an unknown control action: %s", request.action)
        return None
    if not request.cuts_the_turn:
        control.answer({"ok": True, "cut": False})
        control.hold(request)
        return None
    control.answer({"ok": True, "cut": True})
    return request


def boundary_requested() -> Request | None:
    """A reload outstanding at a state boundary, or None. Never raises.

    Every reload is honoured here, `--at-boundary` or not: the boundary is where a request
    that arrived while a script node ran, or one the stream loop held, is finally acted on.
    """
    request = control.outstanding()
    if request is None:
        return None
    if request.action != ACTION:
        control.answer({"error": f"this run does not know the action {request.action!r}"})
        logger.warning("ignoring an unknown control action: %s", request.action)
        return None
    control.answer({"ok": True, "cut": False})
    return request


__all__ = [
    "ACTION",
    "RELOAD_EXIT_CODE",
    "ReloadRequested",
    "boundary_requested",
    "cut_by",
    "cut_requested",
]
