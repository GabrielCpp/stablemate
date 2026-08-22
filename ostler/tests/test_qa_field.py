"""`qa.field` and the absence it yields — read directly, as the pure walk it is.

The rule these enforce is one sentence: nothing a plan asks about product data may raise.
A `KeyError` inside an assertion is not a failed assertion, it is a dead scenario, and the
obligations it covered come back `unproven` — the run observed nothing — instead of red.
"""

from __future__ import annotations

from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
MISSING = harness.MISSING


def field(data: Any, path: str, **kwargs: Any) -> Any:
    return harness.Qa.field(None, data, path, **kwargs)


BODY = {"claim": {"id": "cl-1001", "holder_uid": "u-1", "tags": ["a", "b"], "note": None}}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("claim", BODY["claim"]),
        ("claim.id", "cl-1001"),
        ("claim.tags.1", "b"),
        ("claim.note", None),
    ],
)
def test_a_path_that_is_there_reads_the_value(path: str, expected: Any) -> None:
    assert field(BODY, path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "claim.holderUid",  # the product spells it differently
        "claim.missing.deeper",
        "claim.tags.9",  # past the end
        "claim.tags.name",  # a name against a sequence
        "claim.id.anything",  # a path through a scalar
        "nothing",
    ],
)
def test_a_path_that_is_not_there_is_missing_rather_than_a_raise(path: str) -> None:
    assert field(BODY, path) is MISSING


def test_a_caller_may_name_its_own_default() -> None:
    assert field(BODY, "claim.holderUid", default="") == ""


def test_missing_answers_every_question_negatively() -> None:
    # This is the whole reason it is not `None`: the assertion that asked is about to call
    # `len()` on it, iterate it, or compare it, and `None` raises on all three.
    absent = field(BODY, "claim.holderUid")
    assert not absent
    assert len(absent) == 0
    assert list(absent) == []
    assert "anything" not in absent
    assert absent["anything"] is MISSING
    assert absent != "u-1"
    assert not absent > 3
    assert not absent < 3
    assert repr(absent) == "<missing>"


def test_an_absence_does_not_even_equal_another_absence() -> None:
    # Otherwise `qa.field(a, "x") == qa.field(b, "x")` passes on a product that dropped the
    # field from both, which is an assertion with no way of going red.
    assert field(BODY, "nope") != field(BODY, "also-nope")
    assert field(BODY, "nope") != BODY["claim"]["id"]
