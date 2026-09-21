"""The reload verb: what an operator's request means to a run that is already going."""

from __future__ import annotations

import logging

from workhorse import control
from workhorse.control import Request

RELOAD_EXIT_CODE = 3

ACTION = "reload"

SWITCH_PROFILE = "switch-profile"

_NOT_BLOCKED: dict[str, object] = {
    "ok": False,
    "error": "this run is not blocked on an operator gate right now",
}

logger = logging.getLogger(__name__)


class ReloadRequested(Exception):
    """An operator asked for pushed code to be picked up."""

    workhorse_control_unwind = True

    def __init__(
        self, message: str = "reload requested", *, core: bool = False, cli: str = ""
    ) -> None:
        super().__init__(message)
        self.core = core
        self.cli = cli


def cut_requested() -> Request | None:
    """A cutting reload, or None; an accepted stop raises KeyboardInterrupt."""
    return cut_by(control.take())


def cut_by(request: Request | None) -> Request | None:
    """The same policy, for a request some other wait already took off the channel."""
    if request is None:
        return None
    if request.action == control.STOP:
        control.answer({"ok": True, "action": control.STOP})
        raise KeyboardInterrupt("stop requested")
    if request.action == SWITCH_PROFILE:
        control.answer(
            {"ok": True, "queued": True, "profile": request.profile, "cut": False}
        )
        control.hold(request)
        return None
    if request.action == control.ANSWER:
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
    """A boundary action, or None; an accepted stop raises KeyboardInterrupt."""
    request = control.outstanding()
    if request is None:
        return None
    if request.action == control.STOP:
        control.answer({"ok": True, "action": control.STOP})
        raise KeyboardInterrupt("stop requested")
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
