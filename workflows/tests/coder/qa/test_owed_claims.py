"""A criterion the books' end review observed nowhere reaches the scenario seat as an owed claim."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coder.qa.conftest import BooksLeft
from coder.qa.test_flow import UNREACHED_CLAIMS

UNSEEN = {"criterion": 2, "verdict": "unobserved", "evidence": "only a load run shows latency"}
UNSEEN_CLAIM = "the thing is fast (acceptance criterion 2, which no book play observed: only a load run shows latency)"


def test_a_criterion_the_book_review_observed_nowhere_is_owed_by_the_scenario_seat(
    qa_after_books: Callable[[dict[str, Any]], BooksLeft],
) -> None:
    """A criterion no play observed still needs a proof, so it joins the claims the seat must cover."""
    agent, owed, _, _ = qa_after_books({"unreached": UNREACHED_CLAIMS[:1], "unobserved": [UNSEEN]})

    assert owed == [UNREACHED_CLAIMS[0], UNSEEN_CLAIM]
    assert agent.calls[:1] == ["qa-story"], agent.calls
    assert agent.args[0]["book_unreached"] == owed


def test_a_record_with_only_an_unobserved_criterion_still_gets_a_seat_turn(
    qa_after_books: Callable[[dict[str, Any]], BooksLeft],
) -> None:
    """Before this, a clean record with nothing unreached passed with no seat turn and no proof."""
    agent, owed, _, _ = qa_after_books({"unobserved": [UNSEEN]})

    assert owed == [UNSEEN_CLAIM]
    assert agent.calls[:1] == ["qa-story"], agent.calls
