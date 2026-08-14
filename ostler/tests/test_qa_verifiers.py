"""What the harness's differential verifiers refuse, called as the functions they are.

These are pure comparisons, so they are exercised directly rather than through a plan in a
subprocess: the thing under test is what counts as *observing* a lifecycle claim, and a whole
run around it would prove the driver works, not that a no-op is caught.
"""

from __future__ import annotations

from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")


@pytest.mark.parametrize("check", ["created", "removed"])
def test_a_lifecycle_check_refuses_an_after_only_observation(check: str) -> None:
    """The after-read alone is the mistake — it passes identically on a subject that was
    already there — so the harness says so at the call rather than asserting presence."""
    with pytest.raises(TypeError) as raised:
        harness.VERIFIERS[check]({"id": "b-1"}, {"subject": "the booking"})
    assert f"{check} observes a change" in str(raised.value)
    assert "(before, after)" in str(raised.value)


@pytest.mark.parametrize(
    ("before", "after", "passes"),
    [
        (None, {"id": "b-1"}, True),
        ([], [{"id": "b-1"}], True),
        # Already there: the pass this check exists to withhold.
        ({"id": "b-0"}, {"id": "b-1"}, False),
        # Nothing happened.
        (None, None, False),
    ],
)
def test_created_is_the_absence_before_and_the_presence_after(
    before: Any, after: Any, passes: bool
) -> None:
    ok, actual, expected = harness.VERIFIERS["created"]((before, after), {"subject": "booking"})
    assert ok is passes
    assert actual == {"before": before, "after": after}
    assert expected == {"before": "absent", "after": "present"}


@pytest.mark.parametrize(
    ("before", "after", "passes"),
    [
        ({"id": "h-1"}, None, True),
        ([{"id": "h-1"}], [], True),
        # Never there: absence afterwards attributes nothing to the action.
        (None, None, False),
        ({"id": "h-1"}, {"id": "h-1"}, False),
    ],
)
def test_removed_is_the_presence_before_and_the_absence_after(
    before: Any, after: Any, passes: bool
) -> None:
    ok, actual, expected = harness.VERIFIERS["removed"]((before, after), {"subject": "hold"})
    assert ok is passes
    assert actual == {"before": before, "after": after}
    assert expected == {"before": "present", "after": "absent"}
