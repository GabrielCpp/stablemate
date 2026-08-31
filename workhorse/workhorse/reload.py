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

#: Move a live run onto another named model set. Not a reload, and deliberately not
#: spelled as one: a reload exists to replace *code*, and the profile is re-read and
#: re-narrowed on every turn by construction, so there is nothing here to swap. It is
#: honoured at the state boundary only — cutting a turn for it would throw away work to
#: reach a decision the very next turn makes anyway.
SWITCH_PROFILE = "switch-profile"

#: The refusal both decision sites give an `answer` when no operator wait holds the
#: channel — the gate the sender is aiming at either does not exist or is not what
#: this run is blocked on, and only the wait itself knows how to consume one.
_NOT_BLOCKED: dict[str, object] = {
    "ok": False,
    "error": "this run is not blocked on an operator gate right now",
}

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

    #: Telemetry says the same thing the paragraph above says. `otel.unwind_to` closes
    #: the spans this raise left open without stamping ERROR on any of them, so a
    #: deliberate reload is not counted among a run's failures. The name is
    #: `otel.CONTROL_UNWIND_MARKER`, read off the instance so otel need not import this.
    workhorse_control_unwind = True

    def __init__(
        self, message: str = "reload requested", *, core: bool = False, cli: str = ""
    ) -> None:
        super().__init__(message)
        self.core = core
        #: The agent CLI to come back on, when the operator asked to move the run onto
        #: another one. Empty means "the one it is already using". It rides the exception
        #: for the same reason `core` does: the request was consumed by the read that
        #: delivered it, so nothing on disk can be re-read to recover what it asked for.
        self.cli = cli


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
    if request.action == SWITCH_PROFILE:
        # Never a cut, whatever `--at-boundary` says: the turn already streaming was
        # spawned with the model the old profile named, and killing it would buy the new
        # one nothing that waiting for the next turn does not.
        #
        # Answered here even though the boundary is what applies it — and answered as
        # *queued* rather than as done. The connection this request came in on is dropped
        # by the next `take()`, a select slice away, so a verdict withheld until the
        # boundary would reach nobody; and an "ok" here would claim a switch that the
        # boundary can still refuse.
        control.answer(
            {"ok": True, "queued": True, "profile": request.profile, "cut": False}
        )
        control.hold(request)
        return None
    if request.action == control.ANSWER:
        # Only an operator wait can consume an answer, and this run is not in one.
        # Declined rather than held: the operator is at a prompt right now, and an
        # answer held for some later gate would answer a question not yet asked.
        control.answer(_NOT_BLOCKED)
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
    """A request the state boundary can honour, or None. Never raises.

    Every reload is honoured here, `--at-boundary` or not: the boundary is where a request
    that arrived while a script node ran, or one the stream loop held, is finally acted on.
    A `switch-profile` is returned unanswered, because the frame that applies it is the
    one that knows whether it could be applied and to what — and a switch that was refused
    must not have been acknowledged as one that landed.
    """
    request = control.outstanding()
    if request is None:
        return None
    if request.action == SWITCH_PROFILE:
        return request
    if request.action == control.ANSWER:
        control.answer(_NOT_BLOCKED)
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
    "SWITCH_PROFILE",
    "ReloadRequested",
    "boundary_requested",
    "cut_by",
    "cut_requested",
]
