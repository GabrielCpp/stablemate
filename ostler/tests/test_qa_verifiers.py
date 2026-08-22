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


class _Response:
    """As much of the harness's `Response` as a verifier reads: a status, a body, a URL."""

    def __init__(self, status: int, body: Any, url: str) -> None:
        self.status, self._body, self.url = status, body, url

    def json(self) -> Any:
        return self._body


@pytest.mark.parametrize(
    ("url", "declared", "passes"),
    [
        ("http://localhost:8080/api/claims", "/api/claims", True),
        # The query is not the route: a filtered read answers the same path.
        ("http://localhost:8080/api/claims?mine=1", "/api/claims", True),
        # The pass this argument exists to withhold — a 200 read off the wrong route.
        ("http://localhost:8080/api/claims", "/api/claims/cl-9999", False),
    ],
)
def test_http_status_compares_the_route_that_answered(
    url: str, declared: str, passes: bool
) -> None:
    """`path=` says *which* request answered. Ignoring it lets a scenario that meant to read
    one route and read another observe the same status and call the claim covered."""
    ok, actual, expected = harness.VERIFIERS["http_status"](
        _Response(200, {}, url), {"code": 200, "path": declared}
    )
    assert ok is passes
    assert expected["path"] == declared
    assert actual["path"] == declared if passes else actual["path"] != declared


def test_http_status_refuses_a_bare_status_when_a_path_was_declared() -> None:
    """An integer carries no route, so the declared comparison cannot be made — a scenario
    defect, told at the call rather than filed against the product."""
    with pytest.raises(TypeError) as raised:
        harness.VERIFIERS["http_status"](200, {"code": 200, "path": "/api/claims"})
    assert "which request answered" in str(raised.value)


def test_count_walks_its_subject_into_the_document_it_was_given() -> None:
    """`{"claims": [a, b]}` has one key and two claims. Counting the document instead of the
    subject satisfies `equals=1` while the product returned two — the accidental pass."""
    ok, actual, _ = harness.VERIFIERS["count"](
        {"claims": [{"id": "cl-1"}, {"id": "cl-2"}]}, {"subject": "claims", "equals": 1}
    )
    assert ok is False
    assert actual == 2


def test_count_reads_a_response_body_before_resolving_its_subject() -> None:
    ok, actual, _ = harness.VERIFIERS["count"](
        _Response(200, {"claims": []}, "http://localhost/api/claims"),
        {"subject": "claims", "equals": 0},
    )
    assert ok is True
    assert actual == 0


def test_count_is_red_when_the_document_has_no_such_subject() -> None:
    """The product omitting the collection is a defect of the product, so it goes red rather
    than raising — the shape the scenario handed over was the right one."""
    ok, actual, _ = harness.VERIFIERS["count"](
        {"policies": []}, {"subject": "claims", "equals": 0}
    )
    assert ok is False
    assert actual == {"subject": "claims", "present": False}


def test_count_leaves_an_already_extracted_collection_alone() -> None:
    """A subject no path can address — a CLI's "entries in the ledger" — still counts the
    collection the scenario extracted for it."""
    ok, actual, _ = harness.VERIFIERS["count"](
        [1, 2, 3], {"subject": "entries in the ledger", "equals": 3}
    )
    assert ok is True
    assert actual == 3


def test_json_path_without_a_comparison_is_red_not_green() -> None:
    """`ostler.checks` refuses this call where it is declared. Should one reach the harness
    anyway, an assertion that cannot fail must not report a pass."""
    ok, actual, expected = harness.VERIFIERS["json_path"](
        {"item": {"id": "abc"}}, {"path": "$.item.id"}
    )
    assert ok is False
    assert actual == "abc"
    assert "presence asserts nothing" in expected
