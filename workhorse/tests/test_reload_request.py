"""What a control message means to `reload`: which site acts on it, and what is declined."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workhorse import control, reload  # noqa: E402
from workhorse.control import FakeChannel, Request  # noqa: E402


def _armed(*requests: Request) -> FakeChannel:
    channel = FakeChannel(*requests)
    control.arm(channel)
    return channel


def test_nothing_asked_for_is_not_a_reload() -> None:
    try:
        control.arm(None)
        assert reload.cut_requested() is None
        assert reload.boundary_requested() is None
    finally:
        control.arm(None)


def test_the_default_request_cuts_the_turn() -> None:
    """The default reason for reloading is that the turn is broken, so the default cuts."""
    channel = _armed(Request(action="reload", core=True))
    try:
        found = reload.cut_requested()
        assert found is not None and found.core is True
        assert channel.replies == [{"ok": True, "cut": True}]
    finally:
        control.arm(None)


def test_an_at_boundary_request_is_held_for_the_boundary_not_dropped() -> None:
    """Taking it off the channel consumed it, so declining means remembering it."""
    channel = _armed(Request(action="reload", at_boundary=True))
    try:
        assert reload.cut_requested() is None
        assert channel.replies == [{"ok": True, "cut": False}]
        assert channel.pending == []
        held = reload.boundary_requested()
        assert held is not None and held.at_boundary is True
    finally:
        control.arm(None)


def test_one_request_is_one_reload() -> None:
    _armed(Request(action="reload"))
    try:
        assert reload.boundary_requested() is not None
        assert reload.boundary_requested() is None
    finally:
        control.arm(None)


def test_a_verb_this_run_does_not_know_is_declined_not_obeyed() -> None:
    """A newer CLI talking to an older run must not be able to reload it by accident."""
    channel = _armed(Request(action="quiesce"), Request(action="quiesce"))
    try:
        assert reload.cut_requested() is None
        assert reload.boundary_requested() is None
        assert [set(reply) for reply in channel.replies] == [{"error"}, {"error"}]
    finally:
        control.arm(None)


def test_a_profile_switch_never_cuts_a_turn_and_is_left_for_the_boundary() -> None:
    """The streaming turn was spawned with the model the *old* profile named, so cutting it buys the new one nothing the next turn does not already give."""
    channel = _armed(Request(action=reload.SWITCH_PROFILE, profile="cheap", at_boundary=True))
    try:
        assert reload.cut_requested() is None
        assert channel.replies == [
            {"ok": True, "queued": True, "profile": "cheap", "cut": False}
        ]
        held = reload.boundary_requested()
        assert held is not None and held.profile == "cheap"
        assert len(channel.replies) == 1
    finally:
        control.arm(None)


def test_a_profile_switch_arriving_at_the_boundary_is_not_answered_there_either() -> None:
    channel = _armed(Request(action=reload.SWITCH_PROFILE, profile="cheap"))
    try:
        found = reload.boundary_requested()
        assert found is not None and found.action == reload.SWITCH_PROFILE
        assert channel.replies == []
    finally:
        control.arm(None)


def test_an_answer_outside_an_operator_wait_is_refused_not_held() -> None:
    """Only the wait itself can consume an answer."""
    channel = _armed(
        Request(action=control.ANSWER, path="/runs/x/operator.md", body="main"),
        Request(action=control.ANSWER, path="/runs/x/operator.md", body="main"),
    )
    try:
        assert reload.cut_requested() is None
        assert reload.boundary_requested() is None
        assert channel.replies == [
            {"ok": False, "error": "this run is not blocked on an operator gate right now"},
            {"ok": False, "error": "this run is not blocked on an operator gate right now"},
        ]
    finally:
        control.arm(None)


def test_a_run_that_ended_leaves_nothing_armed() -> None:
    """The installed channel is process-wide; a run that left one armed would hand its socket to whatever ran next in the same process."""
    _armed(Request(action="reload"))
    control.arm(None)
    assert control.armed().fileno() is None
    assert reload.cut_requested() is None


if __name__ == "__main__":
    test_nothing_asked_for_is_not_a_reload()
    test_the_default_request_cuts_the_turn()
    test_an_at_boundary_request_is_held_for_the_boundary_not_dropped()
    test_one_request_is_one_reload()
    test_a_verb_this_run_does_not_know_is_declined_not_obeyed()
    test_a_profile_switch_never_cuts_a_turn_and_is_left_for_the_boundary()
    test_a_profile_switch_arriving_at_the_boundary_is_not_answered_there_either()
    test_an_answer_outside_an_operator_wait_is_refused_not_held()
    test_a_run_that_ended_leaves_nothing_armed()
    print("ok")
