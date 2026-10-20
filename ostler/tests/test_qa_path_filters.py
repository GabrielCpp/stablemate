"""The comparison filters of the path grammar."""

from __future__ import annotations

from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module


@pytest.mark.parametrize(
    ("op", "observed", "selected"),
    [
        ("<", 4, True), ("<", 5, False),
        ("<=", 5, True), ("<=", 6, False),
        (">", 6, True), (">", 5, False),
        (">=", 5, True), (">=", 4, False),
        ("==", 5, True), ("==", 4, False),
        ("!=", 4, True), ("!=", 5, False),
    ],
)
def test_each_filter_operator_selects_by_its_relation(op: str, observed: int, selected: bool) -> None:
    paths = load_harness_module("ostler_qa_paths")

    assert paths.Filter("quantity", 5, op).selects(observed) is selected


@pytest.mark.parametrize("observed", ["3", None, True, [1]])
def test_an_order_operator_never_selects_what_is_no_number(observed: Any) -> None:
    paths = load_harness_module("ostler_qa_paths")

    assert paths.Filter("quantity", 5, "<").selects(observed) is False


def test_a_filter_prints_its_operator_and_offers_a_value_that_it_selects() -> None:
    paths = load_harness_module("ostler_qa_paths")
    below = paths.Filter("quantity", 5, "<")

    assert repr(below) == "[?(@.quantity<5)]"
    assert below.selects(below.satisfying())
    for op in ("!=", ">", ">=", "<=", "=="):
        flt = paths.Filter("quantity", 5, op)
        assert flt.selects(flt.satisfying())
